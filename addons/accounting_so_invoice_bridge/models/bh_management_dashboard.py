# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


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
        orders, date_order inclusive on both ends."""
        self.env.cr.execute("""
            SELECT
                COALESCE(sw.name, 'No Branch')     AS branch,
                COUNT(so.id)                       AS orders,
                COALESCE(SUM(so.amount_total), 0)  AS total
            FROM sale_order so
            LEFT JOIN stock_warehouse sw ON so.x_sale_branch_id = sw.id
            WHERE
                (so.date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (so.date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND so.state NOT IN ('cancel')
            GROUP BY COALESCE(sw.name, 'No Branch')
            ORDER BY total DESC
            LIMIT %s
        """, (date_from, date_to, limit))
        return self.env.cr.dictfetchall()

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
            row['order_lines'] = self._bridge_approval_lines(order)
            row['payment_proofs'] = proofs_by_order.get(order.id, [])

    def _bridge_approval_lines(self, order):
        """Products sold, as the salesperson sees them: no section / note
        lines and no auto-generated Other Income line. `amount` is the
        Selling Price (tax included) when there is one, else the line's
        tax-included total."""
        has_selling_price = 'cim_selling_price' in self.env['sale.order.line']._fields
        result = []
        for line in order.order_line.sorted(lambda l: (l.sequence, l.id)):
            if (line.display_type or not line.product_id
                    or getattr(line, 'cim_hide_from_order_lines', False)):
                continue
            selling = line['cim_selling_price'] if has_selling_price else 0.0
            result.append({
                'product': line.product_id.display_name,
                'quantity': line.product_uom_qty,
                'uom': line.product_uom.name or '',
                'unit_price': line.price_unit,
                'amount': selling or line.price_total,
                'subtotal': line.price_subtotal,
                'taxes': ', '.join(line.tax_id.mapped('name')),
            })
        return result