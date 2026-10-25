# -*- coding: utf-8 -*-
import logging
import re

from odoo import models, fields, api
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class BhManagementDashboard(models.Model):
    _name = 'bh.management.dashboard'
    _description = 'BH Management Dashboard'

    name = fields.Char(string='Dashboard Name', default='Executive Dashboard')

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None):
        """Main method to fetch all KPI data for the dashboard."""
        today = datetime.today()
        if not date_from:
            # Default: 3 calendar months back -> today. Both clients now
            # always send explicit dates (see dashboard.js / periods.js), so
            # this only fires if a caller omits them entirely; kept in sync
            # anyway so nothing silently reverts to an all-zero "this month"
            # view.
            month = today.month - 2
            year = today.year
            while month <= 0:
                month += 12
                year -= 1
            date_from = today.replace(year=year, month=month, day=1).strftime('%Y-%m-%d')
        if not date_to:
            date_to = today.strftime('%Y-%m-%d')

        # Balances (receivable, payable, cash, credit, deposit) are "as of"
        # figures: never look past today, even if the selected period ends in
        # the future (e.g. "This Month" ending on the 30th).
        balance_date = min(date_to, today.strftime('%Y-%m-%d'))

        finance_data = self._get_finance_data(date_from, date_to)
        # Credit / deposit reports live in their own optional modules
        # (customer_credit_report / customer_deposit_credit). They are not
        # hard 'depends' of this module — each getter checks whether the
        # relevant fields exist on res.partner and returns None if not, so
        # the Finance tab simply hides the section instead of erroring out.
        finance_data['customer_credit'] = self._get_customer_credit_data(balance_date)
        finance_data['customer_deposits'] = self._get_customer_deposit_data(balance_date)
        # Cash & Bank balances — a running total as of date_to, not a
        # period movement, so it always reflects the true balance an
        # executive would expect (see _get_cash_at_bank_data docstring).
        finance_data['cash_at_bank'] = self._get_cash_at_bank_data(balance_date)
        # Credit sales = confirmed customer invoices that are not paid yet.
        # A savepoint keeps a failure here from aborting the whole request.
        try:
            with self.env.cr.savepoint():
                finance_data['credit_sales'] = self._get_credit_sales_data(balance_date)
        except Exception:
            _logger.exception("bh_management_dashboard: credit sales failed")
            finance_data['credit_sales'] = None
        # Receivable / Payable — Chart of Accounts balance as of date_to,
        # same approach as Cash & Bank, overriding the invoice-residual
        # figures computed above (see _get_receivable_payable_data
        # docstring for why).
        rp = self._get_receivable_payable_data(balance_date)
        finance_data['summary']['total_receivable'] = rp['total_receivable']
        finance_data['summary']['total_payable'] = rp['total_payable']
        # Drill-down detail for the Receivable/Payable modals — simple
        # per-partner/account open balance, no aging — see
        # _get_receivable_payable_data.
        finance_data['receivable_breakdown'] = rp['receivable_breakdown']
        finance_data['payable_breakdown'] = rp['payable_breakdown']
        # Additive info (not shown by the current UI): credit-side balances
        # that were excluded from the Receivable / Payable headline figures.
        finance_data['receivable_configured'] = rp.get('receivable_configured', True)
        finance_data['payable_configured'] = rp.get('payable_configured', True)
        finance_data['receivable_unapplied_credits'] = rp['unapplied_credits']
        finance_data['payable_unapplied_debits'] = rp['unapplied_debits']

        try:
            company_data = self._get_company_data()
        except Exception:
            # The Company tab must never take the whole dashboard down.
            _logger.exception("bh_management_dashboard: company data failed")
            company_data = None

        return {
            'company':       company_data,
            'sales':         self._get_sales_data(date_from, date_to),
            'inventory':     self._get_inventory_data(),
            'finance':       finance_data,
            'purchase':      self._get_purchase_data(date_from, date_to),
            'manufacturing': self._get_manufacturing_data(date_from, date_to),
            'hr':            self._get_hr_data(),
            'date_from':     date_from,
            'date_to':       date_to,
        }

    def _get_previous_period(self, date_from, date_to):
        """Return (prev_from, prev_to): the period immediately preceding
        [date_from, date_to], same length in days — e.g. 1-30 Sep's
        previous period is 1-31 Aug (31 days back-to-back, no gap/overlap).
        Used to compute period-over-period % change for headline KPIs."""
        d_from = fields.Date.from_string(date_from)
        d_to = fields.Date.from_string(date_to)
        length_days = (d_to - d_from).days + 1
        prev_to = d_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=length_days - 1)
        return fields.Date.to_string(prev_from), fields.Date.to_string(prev_to)

    def _pct_change(self, current, previous):
        """% change from previous -> current, rounded to 1 decimal. None
        when previous is 0/falsy — you can't compute a meaningful percent
        change from a zero base, so the UI shows 'New' instead of a
        divide-by-zero artifact (e.g. infinite % growth)."""
        if not previous:
            return None
        return round(((current - previous) / previous) * 100, 1)

    # ─────────────────────────────────────────────────────────────────────
    # SALES
    # ─────────────────────────────────────────────────────────────────────
    def _get_sales_data(self, date_from, date_to):
        """
        Fetch sales KPIs.

        Key fixes vs original:
        - Use (date_order AT TIME ZONE 'UTC')::date to handle timestamptz
          correctly regardless of server timezone.
        - date_to range is INCLUSIVE: we extend the upper bound to end-of-day
          using  date_order < (date_to::date + 1)  so a sale placed at
          23:59 on date_to is not silently excluded.
        - confirmed_orders: state = 'sale' (confirmed SO) OR state = 'done'
          (locked/fully-invoiced SO) — both represent real confirmed orders.
        - avg_order_value: average over confirmed+done only (not drafts).
        - total_orders: all non-cancelled SO (draft + sent + confirmed + done).
        """
        self.env.cr.execute("""
            SELECT
                COUNT(id)                                                   AS total_orders,
                COALESCE(SUM(amount_total), 0)                              AS total_revenue,
                COUNT(CASE WHEN state IN ('sale','done') THEN 1 END)        AS confirmed_orders,
                COALESCE(
                    AVG(CASE WHEN state IN ('sale','done')
                             THEN amount_total END
                    ), 0
                )                                                           AS avg_order_value
            FROM sale_order
            WHERE
                (date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND state NOT IN ('cancel')
        """, (date_from, date_to))
        summary = self.env.cr.dictfetchone()

        # ── Period-over-period comparison (previous period, same length) ──
        prev_from, prev_to = self._get_previous_period(date_from, date_to)
        self.env.cr.execute("""
            SELECT
                COUNT(id)                                                   AS total_orders,
                COALESCE(SUM(amount_total), 0)                              AS total_revenue
            FROM sale_order
            WHERE
                (date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND state NOT IN ('cancel')
        """, (prev_from, prev_to))
        prev = self.env.cr.dictfetchone()
        comparison = {
            'prev_date_from':    prev_from,
            'prev_date_to':      prev_to,
            'revenue_prev':      prev['total_revenue'],
            'revenue_change_pct': self._pct_change(summary['total_revenue'], prev['total_revenue']),
            'orders_prev':       prev['total_orders'],
            'orders_change_pct': self._pct_change(summary['total_orders'], prev['total_orders']),
        }
        self.env.cr.execute("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', date_order AT TIME ZONE 'UTC'), 'Mon YYYY') AS month,
                DATE_TRUNC('month', date_order AT TIME ZONE 'UTC')                       AS month_date,
                COALESCE(SUM(amount_total), 0)                                           AS revenue,
                COUNT(id)                                                                AS orders
            FROM sale_order
            WHERE
                date_order >= NOW() - INTERVAL '6 months'
                AND state NOT IN ('cancel')
            GROUP BY DATE_TRUNC('month', date_order AT TIME ZONE 'UTC')
            ORDER BY month_date ASC
        """)
        monthly_trend = self.env.cr.dictfetchall()

        # ── Top customers (and dealers) by revenue in period ──
        # custom_contacts_manager (optional) adds the Contact Category. When
        # it is installed, a contact whose category is "Client" is a DEALER
        # on the mobile app, and every other contact is a CUSTOMER, so the
        # two lists never overlap. Without it, customers are all contacts
        # (as before) and no dealer list is sent (the app then says dealer
        # sales are not available).
        has_category = 'contact_type_code' in self.env['res.partner']._fields
        top_customers = self._get_top_partners_by_revenue(
            date_from, date_to,
            "AND COALESCE(rp.contact_type_code, '') <> 'client'"
            if has_category else "",
            'customer')
        result = {
            'summary':       summary,
            'comparison':    comparison,
            'monthly_trend': monthly_trend,
            'top_customers': top_customers,
        }
        if has_category:
            result['top_dealers'] = self._get_top_partners_by_revenue(
                date_from, date_to,
                "AND rp.contact_type_code = 'client'", 'dealer')
        return result

    def _get_top_partners_by_revenue(self, date_from, date_to, extra_where,
                                     alias, limit=10):
        """Total non-cancelled sales per contact in the period, biggest
        first. `extra_where` is a fixed SQL fragment written in this module
        (never user input); `alias` names the first column ('customer' /
        'dealer'), which is what the mobile app reads."""
        assert alias in ('customer', 'dealer')
        self.env.cr.execute("""
            SELECT
                rp.name                            AS %s,
                COALESCE(SUM(so.amount_total), 0)  AS total
            FROM sale_order so
            JOIN res_partner rp ON so.partner_id = rp.id
            WHERE
                (so.date_order AT TIME ZONE 'UTC')::date >= %%s::date
                AND (so.date_order AT TIME ZONE 'UTC')::date <= %%s::date
                AND so.state NOT IN ('cancel')
                %s
            GROUP BY rp.name
            ORDER BY total DESC
            LIMIT %%s
        """ % (alias, extra_where), (date_from, date_to, limit))
        return self.env.cr.dictfetchall()

    # ─────────────────────────────────────────────────────────────────────
    # INVENTORY
    # ─────────────────────────────────────────────────────────────────────
    def _get_stock_value(self):
        """Return (total_value, {location_id: value}) for internal locations.

        value = quantity on hand x product SALES price (lst_price) in the
        current company, i.e. stock valued at selling price, not cost.
        Runs sudo() because the mobile endpoint calls this
        with_user(<executive>) and an executive is not necessarily a stock
        user; the rest of this dashboard reads through raw SQL for the same
        reason.
        """
        rows = self.env['stock.quant'].sudo()._read_group(
            [('location_id.usage', '=', 'internal')],
            ['product_id', 'location_id'],
            ['quantity:sum'],
        )
        products = self.env['product.product'].sudo().with_company(
            self.env.company
        ).browse([product.id for product, _loc, _qty in rows])
        cost = {p.id: p.lst_price or 0.0 for p in products}

        by_location = {}
        for product, location, qty in rows:
            by_location[location.id] = by_location.get(location.id, 0.0) \
                + (qty or 0.0) * cost.get(product.id, 0.0)
        by_location = {k: round(v, 2) for k, v in by_location.items()}
        return round(sum(by_location.values()), 2), by_location

    @staticmethod
    def _merge_stock_by_branch(location_rows, warehouse_names,
                               value_by_location, limit=None):
        """One row per branch: quantity and value of all its internal
        locations added up, biggest first. A location that belongs to no
        warehouse keeps its own full name."""
        merged = {}
        for r in location_rows:
            wid = r.get('warehouse_id')
            key = ('w', wid) if wid else ('l', r['location_id'])
            row = merged.setdefault(key, {
                'location_id': r['location_id'],
                'location': (warehouse_names.get(wid) if wid else None)
                            or r['location'],
                'qty': 0.0,
                'value': 0.0,
            })
            row['qty'] += float(r['qty'] or 0)
            row['value'] += float(value_by_location.get(r['location_id'], 0.0))
        rows = sorted(merged.values(), key=lambda x: x['qty'], reverse=True)
        for row in rows:
            row['value'] = round(row['value'], 2)
        return rows[:limit] if limit else rows

    def _get_inventory_data(self):
        self.env.cr.execute("""
            SELECT
                COUNT(DISTINCT sq.product_id)                   AS total_products,
                COALESCE(SUM(sq.quantity), 0)                   AS total_qty,
                COUNT(CASE WHEN sq.quantity <= 0 THEN 1 END)    AS stockout_count
            FROM stock_quant sq
            JOIN stock_location sl ON sq.location_id = sl.id
            WHERE sl.usage = 'internal'
        """)
        summary = self.env.cr.dictfetchone()

        # Stock value = on-hand quantity x product sales price (lst_price). It deliberately does NOT sum
        # stock.valuation.layer: layers are empty/zero when stock came in
        # via inventory adjustment or opening import, or while the product
        # cost was still 0, which made this card show 0.00.
        total_value, value_by_location = self._get_stock_value()
        summary['total_value'] = total_value

        self.env.cr.execute("""
            SELECT
                sl.id                              AS location_id,
                sl.complete_name                   AS location,
                sl.warehouse_id                    AS warehouse_id,
                COALESCE(SUM(sq.quantity), 0)      AS qty
            FROM stock_quant sq
            JOIN stock_location sl ON sq.location_id = sl.id
            WHERE sl.usage = 'internal'
            GROUP BY sl.id, sl.complete_name, sl.warehouse_id
        """)
        location_rows = self.env.cr.dictfetchall()
        # Show the BRANCH (warehouse) name, e.g. "Koye Branch", not the short
        # technical location code ("WH/Stock"). Sub-locations of one branch
        # are added together. Same names as "Top Branches by Sales".
        warehouse_ids = {r['warehouse_id'] for r in location_rows
                         if r['warehouse_id']}
        warehouse_names = {
            w.id: w.name for w in
            self.env['stock.warehouse'].sudo().browse(list(warehouse_ids)).exists()
        }
        by_location = self._merge_stock_by_branch(
            location_rows, warehouse_names, value_by_location)

        self.env.cr.execute("""
            SELECT
                pt.name->>'en_US'              AS product,
                COALESCE(SUM(sq.quantity), 0)  AS qty_on_hand,
                pp.id                          AS product_id
            FROM stock_quant sq
            JOIN stock_location sl  ON sq.location_id = sl.id
            JOIN product_product pp ON sq.product_id  = pp.id
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            WHERE sl.usage = 'internal'
            GROUP BY pt.name, pp.id
            HAVING SUM(sq.quantity) < 10 AND SUM(sq.quantity) >= 0
            ORDER BY qty_on_hand ASC
            LIMIT 10
        """)
        low_stock = self.env.cr.dictfetchall()

        return {
            'summary':     summary,
            'by_location': by_location,
            'low_stock':   low_stock,
        }

    # ─────────────────────────────────────────────────────────────────────
    # FINANCE
    # ─────────────────────────────────────────────────────────────────────
    def _get_finance_data(self, date_from, date_to):
        """
        Fix: use invoice_date (DATE column — no timezone cast needed).

        total_receivable / total_payable are NOT computed here anymore —
        they used to be summed from account_move.amount_residual, bounded
        by the same invoice_date window as total_invoices/total_invoiced,
        which contradicted their own "lifetime, not date-filtered" intent
        (an unpaid invoice from an earlier period would silently drop out
        of Receivables the moment the dashboard period moved past it).
        They are now overwritten by get_dashboard_data() with the Chart
        of Accounts balance from _get_receivable_payable_data(), matching
        the Cash & Bank approach. See that method's docstring for why.
        """
        # Period summary
        self.env.cr.execute("""
            SELECT
                COUNT(CASE WHEN move_type = 'out_invoice' AND state = 'posted' THEN 1 END)
                                                                AS total_invoices,
                COALESCE(SUM(
                    CASE WHEN move_type = 'out_invoice' AND state = 'posted'
                         THEN amount_total_signed ELSE 0 END
                ), 0)                                           AS total_invoiced
            FROM account_move
            WHERE company_id = %s
              AND invoice_date BETWEEN %s::date AND %s::date
        """, (self.env.company.id, date_from, date_to))
        summary = self.env.cr.dictfetchone()

        # ── Period-over-period comparison (previous period, same length) ──
        prev_from, prev_to = self._get_previous_period(date_from, date_to)
        self.env.cr.execute("""
            SELECT
                COALESCE(SUM(
                    CASE WHEN move_type = 'out_invoice' AND state = 'posted'
                         THEN amount_total_signed ELSE 0 END
                ), 0)                                           AS total_invoiced
            FROM account_move
            WHERE company_id = %s
              AND invoice_date BETWEEN %s::date AND %s::date
        """, (self.env.company.id, prev_from, prev_to))
        prev = self.env.cr.dictfetchone()
        comparison = {
            'prev_date_from':     prev_from,
            'prev_date_to':       prev_to,
            'invoiced_prev':      prev['total_invoiced'],
            'invoiced_change_pct': self._pct_change(summary['total_invoiced'], prev['total_invoiced']),
        }

        # Monthly trend — last 6 months
        self.env.cr.execute("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', invoice_date), 'Mon YYYY') AS month,
                DATE_TRUNC('month', invoice_date)                       AS month_date,
                COALESCE(SUM(
                    CASE WHEN move_type = 'out_invoice' THEN amount_total ELSE 0 END
                ), 0)                                                   AS invoiced,
                COALESCE(SUM(
                    CASE WHEN move_type = 'in_invoice' THEN amount_total ELSE 0 END
                ), 0)                                                   AS bills
            FROM account_move
            WHERE state       = 'posted'
              AND invoice_date >= (CURRENT_DATE - INTERVAL '6 months')::date
              AND move_type   IN ('out_invoice', 'in_invoice')
            GROUP BY DATE_TRUNC('month', invoice_date)
            ORDER BY month_date ASC
        """)
        monthly_trend = self.env.cr.dictfetchall()

        return {
            'summary':       summary,
            'comparison':    comparison,
            'monthly_trend': monthly_trend,
        }

    # ─────────────────────────────────────────────────────────────────────
    # CASH AT BANK
    # ─────────────────────────────────────────────────────────────────────
    def _get_cash_at_bank_data(self, date_to):
        """Cash & Bank balances, one row per Bank/Cash journal.

        A bank balance is a running total, not a period movement, so unlike
        the sales/purchase/finance summaries above this is NOT bounded by
        date_from — it sums every posted entry on the journal's account
        from inception through date_to. That means switching the dashboard
        period still shows "balance as of the end of that period" rather
        than zeroing out for any period that isn't the current month.

        Journals with no default_account_id (misconfigured) or no posted
        entries yet simply show a balance of 0 — they are not excluded, so
        the bank still appears in the list.

        The balance per journal is the standard General Ledger balance of
        that journal's linked account (default_account_id) — i.e. exactly
        what Odoo's own "Balance" smart button shows on that account in
        Chart of Accounts. That means it is NOT restricted to entries
        posted through this specific journal: opening-balance entries,
        inter-journal transfers, and reconciliation entries posted via
        another journal (e.g. Miscellaneous) but hitting this account are
        correctly included too, matching what an accountant would expect
        when they look up "what's the balance of account 101105".

        Caveat: if two Bank/Cash journals were ever configured to share the
        SAME default_account_id (not the normal setup — each journal
        Odoo creates gets its own dedicated account), both rows would show
        that account's full balance and the total would double-count it.
        Standard journal setup (one dedicated account per journal, as in
        your Bank journal → 101105 LCMA) does not hit this.

        aj.name (like product/department names elsewhere in this file) is
        a translated field, so on multi-language databases Postgres
        stores it as jsonb — hence the ->>'en_US' extraction with a
        fallback to the raw value for single-language databases where
        it's a plain varchar.
        """
        self.env.cr.execute("""
            SELECT
                aj.id                                          AS journal_id,
                COALESCE(aj.name->>'en_US', aj.name::text)     AS bank_name,
                aj.type                                        AS journal_type,
                rb.acc_number                                  AS account_number,
                rbk.name                                       AS bank_provider,
                COALESCE(SUM(aml.balance), 0)                  AS balance
            FROM account_journal aj
            LEFT JOIN account_account aa
                   ON aa.id = aj.default_account_id
            LEFT JOIN res_partner_bank rb
                   ON rb.id = aj.bank_account_id
            LEFT JOIN res_bank rbk
                   ON rbk.id = rb.bank_id
            LEFT JOIN account_move_line aml
                   ON aml.account_id  = aa.id
                  AND aml.parent_state = 'posted'
                  AND aml.company_id  = aj.company_id
                  AND aml.date       <= %s::date
            WHERE aj.type IN ('bank', 'cash')
              AND aj.company_id = %s
            GROUP BY aj.id, aj.name, aj.type, rb.acc_number, rbk.name
            ORDER BY balance DESC
        """, (date_to, self.env.company.id))
        banks = self.env.cr.dictfetchall()

        total_balance = sum(b['balance'] for b in banks)

        return {
            'total_balance': total_balance,
            'bank_count':    len(banks),
            'as_of':         date_to,
            'banks': [{
                'id':             b['journal_id'],
                'name':           b['bank_name'],
                'type':           b['journal_type'],  # 'bank' | 'cash'
                'account_number': b['account_number'],
                'bank_provider':  b['bank_provider'],
                'balance':        b['balance'],
            } for b in banks],
        }

    # ─────────────────────────────────────────────────────────────────────
    # RECEIVABLE / PAYABLE
    # ─────────────────────────────────────────────────────────────────────
    def _get_receivable_payable_data(self, date_to):
        """Receivable & Payable as of date_to, from the General Ledger
        (posted journal items on 'asset_receivable' / 'liability_payable'
        accounts).

        Balances are first grouped per (partner, account) — the same
        grouping the drill-down modal uses — and only then summed:

          * Receivable = sum of the POSITIVE (debit-side) balances, i.e.
            what customers actually owe us.
          * Payable    = sum of the POSITIVE amounts owed (credit-side
            balances, sign-flipped), i.e. what we actually owe vendors.

        Opposite-side balances (customer advances / unapplied payments /
        unapplied credit notes on receivable accounts, vendor
        overpayments on payable accounts) are NOT netted against the
        headline figure. Netting them is what previously produced a
        negative "Accounts Receivable" total while every row in the
        drill-down list was positive. They are returned separately as
        'unapplied_credits' / 'unapplied_debits' for reference.

        The KPI total and the drill-down modal now use exactly the same
        population of lines (all posted lines up to date_to), so the total
        always equals the sum of the rows in the modal.

        Like Cash & Bank, this is a point-in-time balance as of date_to,
        NOT bounded by date_from.
        """
        self.env.cr.execute("""
            WITH bal AS (
                SELECT aa.account_type,
                       aml.partner_id,
                       aml.account_id,
                       SUM(aml.balance) AS bal
                FROM account_move_line aml
                JOIN account_account aa
                  ON aa.id = aml.account_id
                WHERE aa.account_type IN ('asset_receivable', 'liability_payable')
                  AND aml.parent_state = 'posted'
                  AND aml.company_id  = %s
                  AND aml.date       <= %s::date
                GROUP BY aa.account_type, aml.partner_id, aml.account_id
            )
            SELECT
                COALESCE(SUM(CASE WHEN account_type = 'asset_receivable'
                                   AND bal > 0 THEN bal ELSE 0 END), 0)
                    AS total_receivable,
                COALESCE(SUM(CASE WHEN account_type = 'asset_receivable'
                                   AND bal < 0 THEN -bal ELSE 0 END), 0)
                    AS unapplied_credits,
                COALESCE(SUM(CASE WHEN account_type = 'liability_payable'
                                   AND bal < 0 THEN -bal ELSE 0 END), 0)
                    AS total_payable,
                COALESCE(SUM(CASE WHEN account_type = 'liability_payable'
                                   AND bal > 0 THEN bal ELSE 0 END), 0)
                    AS unapplied_debits
            FROM bal
        """, (self.env.company.id, date_to))
        row = self.env.cr.dictfetchone()

        return {
            'total_receivable':  row['total_receivable'],
            'total_payable':     row['total_payable'],
            'unapplied_credits': row['unapplied_credits'],
            'unapplied_debits':  row['unapplied_debits'],
            'as_of':             date_to,
            'receivable_breakdown': self._partner_balance_breakdown(
                'asset_receivable', date_to, negate=False
            ),
            'payable_breakdown': self._partner_balance_breakdown(
                'liability_payable', date_to, negate=True
            ),
        }

    def _partner_balance_breakdown(self, account_type, date_to, negate=False):
        """Per-partner (or per-account, when no partner is set) balance
        for one account type — just a name and a total, ordered by size.
        No due-date/aging logic.

        Uses the SAME population as the KPI total in
        _get_receivable_payable_data (all posted lines up to date_to) and
        only lists rows whose amount is positive ("amount owed"), so the
        rows add up to the headline figure. The row count is also what the
        card caption ("N customers / N vendors") displays, so the list is
        no longer cut at 15 rows (capped at 500 as a safety limit; the
        modal scrolls).

        Many lines here have no res.partner attached at all — this company's
        Chart of Accounts uses a dedicated named account per payee instead
        (e.g. "221001 — Ousman Endrise" as its own Payable account), rather
        than always tagging a partner on the journal item. So the row label
        falls back to the GL account's own name in that case, instead of a
        generic "Unknown Partner" that would lump unrelated payees together.
        Grouping by account (not just partner) keeps those rows separate.

        `negate` flips the sign for liability_payable (credit-normal) so
        amounts read as positive "amount owed", matching the KPI totals.
        `sign` below is a hardcoded '1'/'-1' set internally — never user
        input — so splicing it into the query text is safe.

        account_account.name is a TRANSLATABLE field, stored as jsonb
        (e.g. {"en_US": "Ousman Endrise"}) — unlike res_partner.name, a
        plain varchar. COALESCE(rp.name, aa.name) mixes those two types
        and Postgres rejects it outright ("COALESCE types character
        varying and jsonb cannot be matched"). aa.name->>lang pulls the
        text out for one language, with a chain of fallbacks in case the
        user's language has no translation stored for that account.
        """
        sign = '-1' if negate else '1'
        lang = self.env.user.lang or self.env.context.get('lang') or 'en_US'
        self.env.cr.execute(f"""
            SELECT
                COALESCE(
                    rp.name,
                    aa.name->>%(lang)s,
                    aa.name->>'en_US',
                    (SELECT v FROM jsonb_each_text(aa.name) AS t(k, v) LIMIT 1)
                )                                                    AS partner_name,
                COALESCE(SUM({sign} * aml.balance), 0)                AS total
            FROM account_move_line aml
            JOIN account_account aa
              ON aa.id = aml.account_id
            LEFT JOIN res_partner rp
              ON rp.id = aml.partner_id
            WHERE aa.account_type = %(account_type)s
              AND aml.parent_state = 'posted'
              AND aml.company_id  = %(company_id)s
              AND aml.date       <= %(date_to)s::date
            GROUP BY rp.id, rp.name, aa.id, aa.name
            HAVING COALESCE(SUM({sign} * aml.balance), 0) > 0
            ORDER BY total DESC
            LIMIT 500
        """, {
            'date_to':      date_to,
            'account_type': account_type,
            'company_id':   self.env.company.id,
            'lang':         lang,
        })
        return self.env.cr.dictfetchall()

    # ─────────────────────────────────────────────────────────────────────
    # CREDIT / DEPOSIT  —  break-down helpers
    #
    # Everything below is driven ONLY by the accounts selected in
    # Executive Dashboard > Configuration > Finance Accounts. A category
    # with no accounts selected shows nothing (never a fallback to "all").
    # ─────────────────────────────────────────────────────────────────────
    def _breakdown_account_rows(self, accounts, date_to, negate=False):
        """Posted ledger balance, as of date_to, of each selected account.

        `negate` flips the sign for credit-normal accounts (deposits), so a
        positive number always means "money held / owed" in the card's sense.
        """
        if not accounts:
            return []
        self.env.cr.execute("""
            SELECT aml.account_id, COALESCE(SUM(aml.balance), 0)
            FROM account_move_line aml
            WHERE aml.account_id = ANY(%s::int[])
              AND aml.parent_state = 'posted'
              AND aml.company_id  = %s
              AND aml.date       <= %s::date
            GROUP BY aml.account_id
        """, (accounts.ids, self.env.company.id, date_to))
        balances = dict(self.env.cr.fetchall())
        sign = -1.0 if negate else 1.0
        rows = [{
            'id':      a.id,
            'code':    a.code,
            'name':    a.name,
            'balance': sign * balances.get(a.id, 0.0),
        } for a in accounts.sudo().with_company(self.env.company)]
        rows.sort(key=lambda r: r['balance'], reverse=True)
        return rows

    _STAFF_PREFIX = re.compile(
        r'^\s*staff?\s+(?:receivable|recivable|receivale|debtor)(?=[\s\-:(])[\s\-:(]*',
        re.I)
    _CUSTOMER_PREFIX = re.compile(r'^\s*customer(?=[\s\-:])[\s\-:]*', re.I)

    @api.model
    def _clean_account_name(self, name):
        """Display name for a ledger line that has no contact: the account
        name without the code and without the 'STAFF RECEIVABLE' / 'STAFF
        DEBTOR' / 'Customer' label. Anything that doesn't match safely is
        left as is."""
        name = (name or '').strip()
        out = self._STAFF_PREFIX.sub('', name)
        out = self._CUSTOMER_PREFIX.sub('', out)
        if out.count(')') > out.count('('):
            out = out.rstrip(' )')
        return out.strip() or name

    def _group_balances(self, accounts, date_to, negate=False):
        """Who holds a balance on `accounts`: one entry per partner (or per
        account when a posted line has no partner), positive amounts only.

        Returns [{'partner_id', 'amount', 'account'}] sorted by amount.
        'account' is the cleaned-up NAME (no code) of the account carrying
        most of it.
        """
        if not accounts:
            return []
        self.env.cr.execute("""
            SELECT aml.partner_id, aml.account_id, COALESCE(SUM(aml.balance), 0)
            FROM account_move_line aml
            WHERE aml.account_id = ANY(%s::int[])
              AND aml.parent_state = 'posted'
              AND aml.company_id  = %s
              AND aml.date       <= %s::date
            GROUP BY aml.partner_id, aml.account_id
            HAVING ABS(SUM(aml.balance)) > 0.005
        """, (accounts.ids, self.env.company.id, date_to))
        # Read the result set NOW. Reading a.code / a.name below runs more
        # queries on this same cursor, which would discard these rows.
        ledger = self.env.cr.fetchall()
        names = {a.id: a.name or ''
                 for a in accounts.sudo().with_company(self.env.company)}
        sign = -1.0 if negate else 1.0
        per = {}
        for pid, aid, bal in ledger:
            key = ('p', pid) if pid else ('a', aid)
            entry = per.setdefault(
                key, {'partner_id': pid, 'amount': 0.0, 'by_account': {}})
            entry['amount'] += sign * bal
            entry['by_account'][aid] = abs(bal)
        out = []
        for entry in per.values():
            if entry['amount'] <= 0.01:
                continue
            aid = max(entry['by_account'], key=entry['by_account'].get)
            out.append({
                'partner_id': entry['partner_id'],
                'amount':     entry['amount'],
                'account':    self._clean_account_name(names.get(aid, '')),
            })
        out.sort(key=lambda e: e['amount'], reverse=True)
        return out

    def _partner_group_rows(self, entries, builder):
        """Turn _group_balances() entries into table rows. `builder(partner,
        entry)` returns the row dict; partner is False for ledger lines that
        carry no partner."""
        Partner = self.env['res.partner']
        ids = [e['partner_id'] for e in entries if e['partner_id']]
        partners = {p.id: p for p in Partner.browse(ids)}
        return [builder(partners.get(e['partner_id']), e) for e in entries[:500]]

    # ─────────────────────────────────────────────────────────────────────
    # CREDIT
    # ─────────────────────────────────────────────────────────────────────
    def _get_customer_credit_data(self, date_to=None):
        """Outstanding credit, split into 'From Customers' and 'From Staff'.

        Each side is the balance held on the accounts selected for it in
        Configuration > Finance Accounts, and nothing else. Invoiced / Paid /
        Orders are the per-contact figures of 'customer_credit_report' when
        that module is installed (0 otherwise).
        """
        date_to = date_to or fields.Date.today().strftime('%Y-%m-%d')
        cfg = self._finance_config()

        def builder(p, e):
            return {
                'name':           p.name if p else e['account'],
                'total_invoiced': getattr(p, 'x_total_invoiced', 0.0) if p else 0.0,
                'amount_paid':    getattr(p, 'x_credit_amount_paid', 0.0) if p else 0.0,
                'outstanding':    e['amount'],
            }

        def group(label, accounts):
            entries = self._group_balances(accounts, date_to)
            return {
                'label': label,
                'total': sum(e['amount'] for e in entries),
                'count': len(entries),
                'rows':  self._partner_group_rows(entries, builder),
                'hint':  ('No outstanding credit on the selected accounts.'
                          if accounts else
                          'No accounts selected. Add them under '
                          'Configuration > Finance Accounts.'),
            }

        customer = group('From Customers', cfg.credit_customer_account_ids)
        staff = group('From Staff', cfg.credit_staff_account_ids)
        rows = customer['rows'] + staff['rows']
        return {
            'configured': bool(cfg.credit_customer_account_ids
                               or cfg.credit_staff_account_ids),
            'summary': {
                'customer_count':    customer['count'] + staff['count'],
                'total_outstanding': customer['total'] + staff['total'],
                'total_invoiced':    sum(r['total_invoiced'] for r in rows),
                'total_paid':        sum(r['amount_paid'] for r in rows),
            },
            'breakdown': {'customer': customer, 'staff': staff},
        }

    # ─────────────────────────────────────────────────────────────────────
    # DEPOSIT
    # ─────────────────────────────────────────────────────────────────────
    def _get_customer_deposit_data(self, date_to=None):
        """Customer deposits from the accounts selected in
        Configuration > Finance Accounts > Deposit - Customer Accounts.

        These are typically liability / payable-type accounts that hold
        advances paid by customers (money the company still owes them).
        We return partner-level positive balances (negate=True so a credit
        balance becomes a positive "deposit held" figure).

        Owner accounts are still returned under breakdown.owner for
        backward compatibility, but the mobile Deposit tab focuses only
        on the customer side.
        """
        date_to = date_to or fields.Date.today().strftime('%Y-%m-%d')
        cfg = self._finance_config()

        def builder(p, e):
            return {
                'name':    p.name if p else e['account'],
                'balance': e['amount'],
            }

        # ── Customer deposits (main report) ─────────────────────────────
        cust_accounts = cfg.deposit_customer_account_ids
        entries = self._group_balances(cust_accounts, date_to, negate=True)
        cust_rows = self._partner_group_rows(entries, builder)
        customer_total = sum(e['amount'] for e in entries)
        customer = {
            'label': 'Customers',
            'total': customer_total,
            'count': len(entries),
            'rows':  cust_rows,
            'hint':  ('No deposit balance on the selected accounts.'
                      if cust_accounts else
                      'No accounts selected. Add them under '
                      'Configuration > Finance Accounts.'),
        }

        # ── Owner (kept for compatibility, not shown on new mobile UI) ──
        owner_accounts = cfg.deposit_owner_account_ids
        owner_rows = self._breakdown_account_rows(
            owner_accounts, date_to, negate=True)
        owner = {
            'label': 'From Owner',
            'total': sum(r['balance'] for r in owner_rows),
            'count': len(owner_rows),
            'rows':  owner_rows,
            'hint':  'No accounts selected. Add them under '
                     'Configuration > Finance Accounts.',
        }

        return {
            'configured': bool(cust_accounts),
            'summary': {
                # Primary KPIs used by the redesigned mobile Deposit tab
                'total_balance':  customer_total,
                'customer_count': customer['count'],
                # Kept for any older client that still reads these keys
                'total_paid':     0.0,
                'total_refunded': 0.0,
            },
            'breakdown': {
                'customer': customer,
                'owner': owner,
            },
        }

    # ─────────────────────────────────────────────────────────────────────
    # PURCHASE
    # ─────────────────────────────────────────────────────────────────────
    def _get_purchase_data(self, date_from, date_to):
        self.env.cr.execute("""
            SELECT
                COUNT(id)                                               AS total_orders,
                COALESCE(SUM(amount_total), 0)                          AS total_spent,
                COUNT(CASE WHEN state IN ('purchase','done') THEN 1 END) AS confirmed,
                COUNT(CASE WHEN state IN ('draft','sent')    THEN 1 END) AS rfqs
            FROM purchase_order
            WHERE
                (date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND state NOT IN ('cancel')
        """, (date_from, date_to))
        summary = self.env.cr.dictfetchone()

        # ── Period-over-period comparison (previous period, same length) ──
        prev_from, prev_to = self._get_previous_period(date_from, date_to)
        self.env.cr.execute("""
            SELECT
                COALESCE(SUM(amount_total), 0)  AS total_spent
            FROM purchase_order
            WHERE
                (date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND state NOT IN ('cancel')
        """, (prev_from, prev_to))
        prev = self.env.cr.dictfetchone()
        comparison = {
            'prev_date_from':  prev_from,
            'prev_date_to':    prev_to,
            'spent_prev':      prev['total_spent'],
            'spent_change_pct': self._pct_change(summary['total_spent'], prev['total_spent']),
        }

        self.env.cr.execute("""
            SELECT
                rp.name                            AS vendor,
                COALESCE(SUM(po.amount_total), 0)  AS total
            FROM purchase_order po
            JOIN res_partner rp ON po.partner_id = rp.id
            WHERE
                (po.date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (po.date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND po.state NOT IN ('cancel')
            GROUP BY rp.name
            ORDER BY total DESC
            LIMIT 5
        """, (date_from, date_to))
        top_vendors = self.env.cr.dictfetchall()

        return {
            'summary':    summary,
            'comparison': comparison,
            'top_vendors': top_vendors,
        }

    # ─────────────────────────────────────────────────────────────────────
    # MANUFACTURING
    # ─────────────────────────────────────────────────────────────────────
    def _get_manufacturing_data(self, date_from, date_to):
        self.env.cr.execute("""
            SELECT
                COUNT(mp.id)                                            AS total_orders,
                COUNT(CASE WHEN mp.state = 'done'      THEN 1 END)     AS completed,
                COUNT(CASE WHEN mp.state = 'progress'  THEN 1 END)     AS in_progress,
                COUNT(CASE WHEN mp.state = 'confirmed' THEN 1 END)     AS planned,
                COALESCE(SUM(mp.product_qty), 0)                       AS total_qty_planned,
                COALESCE(SUM(
                    CASE WHEN mp.state = 'done'
                         THEN mp.product_qty
                         ELSE mp.qty_producing
                    END
                ), 0)                                                  AS total_qty_produced
            FROM mrp_production mp
            WHERE
                COALESCE(
                    (mp.date_start   AT TIME ZONE 'UTC')::date,
                    (mp.date_finished AT TIME ZONE 'UTC')::date
                ) BETWEEN %s::date AND %s::date
                AND mp.state NOT IN ('cancel')
        """, (date_from, date_to))
        summary = self.env.cr.dictfetchone()

        self.env.cr.execute("""
            SELECT
                pt.name->>'en_US'                   AS product,
                COALESCE(SUM(
                    CASE WHEN mp.state = 'done'
                         THEN mp.product_qty
                         ELSE mp.qty_producing
                    END
                ), 0)                              AS produced
            FROM mrp_production mp
            JOIN product_product pp ON mp.product_id     = pp.id
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            WHERE
                COALESCE(
                    (mp.date_start    AT TIME ZONE 'UTC')::date,
                    (mp.date_finished AT TIME ZONE 'UTC')::date
                ) BETWEEN %s::date AND %s::date
                AND mp.state = 'done'
            GROUP BY pt.name
            ORDER BY produced DESC
            LIMIT 5
        """, (date_from, date_to))
        by_product = self.env.cr.dictfetchall()

        return {
            'summary':    summary,
            'by_product': by_product,
        }

    # ─────────────────────────────────────────────────────────────────────
    # HR
    # ─────────────────────────────────────────────────────────────────────
    def _get_hr_data(self):
        self.env.cr.execute("""
            SELECT
                COUNT(CASE WHEN active = true THEN 1 END)                         AS total_employees,
                COUNT(DISTINCT CASE WHEN active = true THEN department_id END)     AS total_departments,
                COUNT(CASE WHEN active = true AND gender = 'male'   THEN 1 END)   AS male_count,
                COUNT(CASE WHEN active = true AND gender = 'female' THEN 1 END)   AS female_count
            FROM hr_employee
            WHERE company_id = %s
        """, (self.env.company.id,))
        summary = self.env.cr.dictfetchone()

        self.env.cr.execute("""
            SELECT
                COALESCE(
                    hd.name->>'en_US',
                    hd.name::text,
                    'Unknown'
                )          AS department,
                COUNT(he.id) AS count
            FROM hr_employee he
            JOIN hr_department hd ON he.department_id = hd.id
            WHERE he.active = true AND he.company_id = %s
            GROUP BY hd.name
            ORDER BY count DESC
            LIMIT 8
        """, (self.env.company.id,))
        by_department = self.env.cr.dictfetchall()

        return {
            'summary':       summary,
            'by_department': by_department,
        }