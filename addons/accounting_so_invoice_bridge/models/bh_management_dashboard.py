# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)

# Products listed per branch in the mobile app's branch popup (safety cap;
# the app pages through them).
BRANCH_PRODUCT_LIMIT = 200


class BhManagementDashboard(models.Model):
    """Adds "Top Branches by Sales" to the Executive Dashboard's Sales tab,
    and completes the rows of the Approvals tab (used by the mobile app).

    The Branch field (sale.order.x_sale_branch_id) is defined in this
    module, and this module already depends (through sale_credit_approval)
    on bh_management_dashboard. Extending the dashboard from here keeps the
    dependency one-way: bh_management_dashboard knows nothing about
    branches and simply hides the panel if `top_branches` is missing.
    """
    _inherit = 'bh.management.dashboard'

    def _get_sales_data(self, date_from, date_to):
        data = super()._get_sales_data(date_from, date_to)
        data['top_branches'] = self._get_top_branches(date_from, date_to)
        return data

    def _get_top_branches(self, date_from, date_to, limit=10):
        """Total sales per Branch (the branch where the sale happened, NOT
        the Deduction Branch the stock leaves from), using exactly the same
        period and filters as the Top Customers query: non-cancelled
        orders, date_order inclusive on both ends.

        Each row also carries `products` (what that branch sold, see
        _get_branch_products) for the mobile app's branch detail popup.
        `branch_id` is the warehouse id, or None for the "No Branch" row."""
        self.env.cr.execute("""
            SELECT
                sw.id                              AS branch_id,
                COALESCE(sw.name, 'No Branch')     AS branch,
                COUNT(so.id)                       AS orders,
                COALESCE(SUM(so.amount_total), 0)  AS total
            FROM sale_order so
            LEFT JOIN stock_warehouse sw ON so.x_sale_branch_id = sw.id
            WHERE
                (so.date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (so.date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND so.state NOT IN ('cancel')
            GROUP BY sw.id, sw.name
            ORDER BY total DESC
            LIMIT %s
        """, (date_from, date_to, limit))
        branches = self.env.cr.dictfetchall()
        try:
            with self.env.cr.savepoint():
                products = self._get_branch_products(
                    date_from, date_to, [b['branch_id'] for b in branches])
        except Exception:
            # The branch totals still show; the app says the product list
            # is not available when `products` is None.
            _logger.exception(
                "accounting_so_invoice_bridge: could not build the products "
                "per branch.")
            products = None
        for branch in branches:
            branch['products'] = (None if products is None
                                  else products.get(branch['branch_id'], []))
        return branches

    def _get_branch_products(self, date_from, date_to, branch_ids,
                             limit=BRANCH_PRODUCT_LIMIT):
        """Products sold per Branch, over exactly the orders behind the
        branch totals (same period, same day boundaries, non-cancelled).

        Returns {branch_id (None = No Branch): [{name, quantity, uom,
        orders, amount}]}, biggest amount first. `amount` is tax included
        and includes the product's own Other Income line, so the products
        of a branch add up to the branch total. Section / note lines, down
        payments and the Other Income lines themselves are not listed."""
        if not branch_ids:
            return {}
        real_ids = [bid for bid in branch_ids if bid]
        self.env.cr.execute("""
            SELECT so.id, so.x_sale_branch_id
            FROM sale_order so
            WHERE
                (so.date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (so.date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND so.state NOT IN ('cancel')
                AND (so.x_sale_branch_id = ANY(%s)
                     OR (%s AND so.x_sale_branch_id IS NULL))
        """, (date_from, date_to, real_ids or [0],
              None in branch_ids))
        branch_of_order = dict(self.env.cr.fetchall())
        if not branch_of_order:
            return {}

        Line = self.env['sale.order.line'].sudo()
        has_hidden = 'cim_hide_from_order_lines' in Line._fields
        has_service = 'cim_service_line_id' in Line._fields
        lines = Line.search([('order_id', 'in', list(branch_of_order)),
                             ('display_type', '=', False),
                             ('product_id', '!=', False)])

        groups = {}  # (branch_id, product_id) -> row
        for line in lines:
            if line.is_downpayment or (has_hidden
                                       and line.cim_hide_from_order_lines):
                continue
            amount = line.price_total
            if has_service and line.cim_service_line_id:
                amount += line.cim_service_line_id.price_total
            product = line.product_id
            qty = line.product_uom_qty
            if line.product_uom and line.product_uom != product.uom_id:
                qty = line.product_uom._compute_quantity(
                    qty, product.uom_id, raise_if_failure=False)
            branch_id = branch_of_order[line.order_id.id] or None
            row = groups.get((branch_id, product.id))
            if row is None:
                row = groups[(branch_id, product.id)] = {
                    'name': product.with_context(
                        display_default_code=False).display_name,
                    'quantity': 0.0,
                    'uom': product.uom_id.name or '',
                    'amount': 0.0,
                    '_orders': set(),
                }
            row['quantity'] += qty
            row['amount'] += amount
            row['_orders'].add(line.order_id.id)

        result = {}
        for (branch_id, _pid), row in groups.items():
            row['orders'] = len(row.pop('_orders'))
            result.setdefault(branch_id, []).append(row)
        for rows in result.values():
            rows.sort(key=lambda r: (-r['amount'], r['name'].lower()))
            del rows[limit:]
        return result

    # ------------------------------------------------------------------
    # Approvals tab: branch, payment term, product lines and payment slips
    # ------------------------------------------------------------------
    def get_dashboard_data(self, date_from=None, date_to=None, **kwargs):
        """Both the web dashboard and the mobile app (/bh_dashboard/mobile/
        get_data) go through this method. sale_credit_approval adds the
        `approvals` block to it; this module is loaded after that one, so by
        the time super() returns, `data['approvals']` is complete and every
        row (action_required + recent) can be enriched with:
          branch          - the order's Branch (where the sale happened)
          payment_term    - the order's payment terms
          amount_tax      - the order's total tax (what Odoo shows on it)
          order_lines     - the products sold (Other Income line left out)
          payment_proofs  - the payment slips (metadata only, no file)
        Rows are matched by their `id` (the sale.order id). A failure here
        must never break the dashboard: the rows are then returned as they
        were, and the error is written to the Odoo log.
        """
        data = super().get_dashboard_data(
            date_from=date_from, date_to=date_to, **kwargs)
        try:
            if isinstance(data, dict):
                self._bridge_enrich_approval_rows(data.get('approvals'))
        except Exception:
            _logger.exception(
                "accounting_so_invoice_bridge: could not add branch / "
                "products / payment proofs to the approval rows.")
        # Customer Credit report (customer_credit_report): live figures,
        # not filtered by the date range.
        if isinstance(data, dict):
            try:
                data['credit'] = self.env['customer.credit.api'].overview()
            except Exception:
                _logger.exception(
                    "accounting_so_invoice_bridge: could not build the "
                    "customer credit report for the dashboard.")
                data['credit'] = None
        return data

    def _bridge_enrich_approval_rows(self, approvals):
        if not isinstance(approvals, dict):
            return
        rows = [row for key in ('action_required', 'recent')
                for row in (approvals.get(key) or []) if isinstance(row, dict)]
        order_ids = {row['id'] for row in rows if row.get('id')}
        if not order_ids:
            return
        # sudo: the executive group has no Sales access of its own.
        orders = {o.id: o for o in
                  self.env['sale.order'].sudo().browse(list(order_ids)).exists()}

        # Which proofs really have a file, without loading the files.
        proofs = self.env['sale.order.payment.proof'].sudo().search(
            [('sale_order_id', 'in', list(orders))])
        with_file = {a['res_id'] for a in self.env['ir.attachment'].sudo()
                     .search_read([
                         ('res_model', '=', 'sale.order.payment.proof'),
                         ('res_field', '=', 'proof_file'),
                         ('res_id', 'in', proofs.ids)], ['res_id'])}
        proofs_by_order = {}
        for proof in proofs.sorted('id'):
            proofs_by_order.setdefault(proof.sale_order_id.id, []).append({
                'id': proof.id,
                'filename': proof.proof_filename or '',
                'kind': proof._preview_kind(proof.proof_filename) or '',
                'has_file': proof.id in with_file,
                'state': proof.state,
                'banks': proof.payment_bank_summary or '',
                'reviewed_by': proof.reviewed_by.name or '',
            })

        for row in rows:
            order = orders.get(row.get('id'))
            if not order:
                continue
            row['branch'] = order.x_sale_branch_id.name or ''
            row['payment_term'] = (order.payment_term_id.name
                                   or row.get('payment_term') or '')
            row['amount_tax'] = order.amount_tax
            row['order_lines'] = self._bridge_approval_lines(order)
            row['payment_proofs'] = proofs_by_order.get(order.id, [])
            # Credit sale: the Credit Sales Report the salesperson sent
            # (latest one; customer_credit_report).
            row['sale_type'] = order.x_sale_type or 'cash'
            report = order.x_credit_request_ids.filtered(
                lambda r: r.state != 'cancelled').sorted(
                lambda r: (r.request_date or r.create_date, r.id))[-1:]
            row['credit_report'] = self.env['customer.credit.api']\
                .request_payload(report, order) if report else None

    def _bridge_approval_lines(self, order):
        """Products sold, as the salesperson sees them: no section / note
        lines and no auto-generated Other Income line. `amount` is the
        Selling Price (tax included) when there is one, else the line's
        tax-included total.

        `tax_amount` is the tax on the line INCLUDING the tax on its own
        Other Income line (the one generated to reach the Selling Price), so
        the amounts of all lines add up to the order's total tax."""
        Line = self.env['sale.order.line']
        has_selling_price = 'cim_selling_price' in Line._fields
        has_service_link = 'cim_service_line_id' in Line._fields
        result = []
        for line in order.order_line.sorted(lambda l: (l.sequence, l.id)):
            if (line.display_type or not line.product_id
                    or getattr(line, 'cim_hide_from_order_lines', False)):
                continue
            selling = line['cim_selling_price'] if has_selling_price else 0.0
            service = line['cim_service_line_id'] if has_service_link else None
            tax_amount = line.price_tax + (service.price_tax if service else 0.0)
            result.append({
                'product': line.product_id.display_name,
                'quantity': line.product_uom_qty,
                'uom': line.product_uom.name or '',
                'unit_price': line.price_unit,
                'amount': selling or line.price_total,
                'subtotal': line.price_subtotal,
                'tax_amount': tax_amount,
                'taxes': ', '.join(line.tax_id.mapped('name')),
            })
        return result