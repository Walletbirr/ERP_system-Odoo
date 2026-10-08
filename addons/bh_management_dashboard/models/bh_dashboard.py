# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


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

        finance_data = self._get_finance_data(date_from, date_to)
        # Credit / deposit reports live in their own optional modules
        # (customer_credit_report / customer_deposit_credit). They are not
        # hard 'depends' of this module — each getter checks whether the
        # relevant fields exist on res.partner and returns None if not, so
        # the Finance tab simply hides the section instead of erroring out.
        finance_data['customer_credit'] = self._get_customer_credit_data()
        finance_data['customer_deposits'] = self._get_customer_deposit_data()
        # Cash & Bank balances — a running total as of date_to, not a
        # period movement, so it always reflects the true balance an
        # executive would expect (see _get_cash_at_bank_data docstring).
        finance_data['cash_at_bank'] = self._get_cash_at_bank_data(date_to)
        # Receivable / Payable — Chart of Accounts balance as of date_to,
        # same approach as Cash & Bank, overriding the invoice-residual
        # figures computed above (see _get_receivable_payable_data
        # docstring for why).
        rp = self._get_receivable_payable_data(date_to)
        finance_data['summary']['total_receivable'] = rp['total_receivable']
        finance_data['summary']['total_payable'] = rp['total_payable']
        # Drill-down detail for the Receivable/Payable modals — simple
        # per-partner/account open balance, no aging — see
        # _get_receivable_payable_data.
        finance_data['receivable_breakdown'] = rp['receivable_breakdown']
        finance_data['payable_breakdown'] = rp['payable_breakdown']

        return {
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

        # ── Top 5 customers by revenue in period ──
        self.env.cr.execute("""
            SELECT
                rp.name                            AS customer,
                COALESCE(SUM(so.amount_total), 0)  AS total
            FROM sale_order so
            JOIN res_partner rp ON so.partner_id = rp.id
            WHERE
                (so.date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (so.date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND so.state NOT IN ('cancel')
            GROUP BY rp.name
            ORDER BY total DESC
            LIMIT 5
        """, (date_from, date_to))
        top_customers = self.env.cr.dictfetchall()

        return {
            'summary':       summary,
            'comparison':    comparison,
            'monthly_trend': monthly_trend,
            'top_customers': top_customers,
        }

    # ─────────────────────────────────────────────────────────────────────
    # INVENTORY
    # ─────────────────────────────────────────────────────────────────────
    def _get_stock_value(self):
        """Return (total_value, {location_id: value}) for internal locations.

        value = quantity on hand x product cost (standard_price) in the
        current company. Runs sudo() because the mobile endpoint calls this
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
        cost = {p.id: p.standard_price or 0.0 for p in products}

        by_location = {}
        for product, location, qty in rows:
            by_location[location.id] = by_location.get(location.id, 0.0) \
                + (qty or 0.0) * cost.get(product.id, 0.0)
        by_location = {k: round(v, 2) for k, v in by_location.items()}
        return round(sum(by_location.values()), 2), by_location

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

        # Stock value = on-hand quantity x current product cost, the same
        # basis as Inventory > Stock overview. It deliberately does NOT sum
        # stock.valuation.layer: layers are empty/zero when stock came in
        # via inventory adjustment or opening import, or while the product
        # cost was still 0, which made this card show 0.00.
        total_value, value_by_location = self._get_stock_value()
        summary['total_value'] = total_value

        self.env.cr.execute("""
            SELECT
                sl.id                              AS location_id,
                sl.complete_name                   AS location,
                COALESCE(SUM(sq.quantity), 0)      AS qty
            FROM stock_quant sq
            JOIN stock_location sl ON sq.location_id = sl.id
            WHERE sl.usage = 'internal'
            GROUP BY sl.id, sl.complete_name
            ORDER BY SUM(sq.quantity) DESC
            LIMIT 6
        """)
        by_location = self.env.cr.dictfetchall()
        for row in by_location:
            row['value'] = value_by_location.get(row['location_id'], 0.0)

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
                         THEN amount_total ELSE 0 END
                ), 0)                                           AS total_invoiced
            FROM account_move
            WHERE invoice_date BETWEEN %s::date AND %s::date
        """, (date_from, date_to))
        summary = self.env.cr.dictfetchone()

        # ── Period-over-period comparison (previous period, same length) ──
        prev_from, prev_to = self._get_previous_period(date_from, date_to)
        self.env.cr.execute("""
            SELECT
                COALESCE(SUM(
                    CASE WHEN move_type = 'out_invoice' AND state = 'posted'
                         THEN amount_total ELSE 0 END
                ), 0)                                           AS total_invoiced
            FROM account_move
            WHERE invoice_date BETWEEN %s::date AND %s::date
        """, (prev_from, prev_to))
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
        """Receivable & Payable, taken from the Chart of Accounts balance
        of every account of type 'asset_receivable' / 'liability_payable'
        — i.e. exactly what Odoo's own "Balance" smart button shows on
        those accounts — same approach as _get_cash_at_bank_data, and for
        the same reason: summing account_move.amount_residual per-invoice
        can drift from the true GL balance (write-offs, manual journal
        entries against the AR/AP account, exchange adjustments, credit
        notes reconciled outside the invoice, etc. all move the account
        balance without necessarily moving amount_residual in lockstep).

        Like Cash & Bank, this is a running total as of date_to, NOT
        bounded by date_from — Receivable/Payable are point-in-time
        balances, not period movements, so switching the dashboard
        period still shows "balance as of the end of that period"
        rather than zeroing out for any period that isn't this month.

        Sign convention: asset_receivable accounts are debit-normal, so
        SUM(balance) is already positive when customers owe money.
        liability_payable accounts are credit-normal, so SUM(balance) is
        negative when the company owes money — negated here so
        total_payable is reported as a positive "amount owed" figure,
        matching how total_receivable reads and how the mobile/web UI
        already expects it.

        Also returns a simple per-partner/account OPEN BALANCE breakdown
        for the drill-down modal (receivable_breakdown / payable_breakdown)
        — just "who" and "how much", no aging/due-date bucketing.

        The breakdown is built from OPEN (unreconciled) lines only, while
        the total_receivable/total_payable KPIs above stay computed from
        ALL posted lines as before, so existing behavior doesn't change;
        the breakdown is additive drill-down detail. In practice the two
        should match closely since reconciled entries net to zero, but
        they can differ by small amounts in edge cases (partial
        reconciliation, exchange adjustments) — the KPI totals remain the
        source of truth.
        """
        self.env.cr.execute("""
            SELECT
                COALESCE(SUM(
                    CASE WHEN aa.account_type = 'asset_receivable'
                         THEN aml.balance ELSE 0 END
                ), 0)  AS total_receivable,
                COALESCE(SUM(
                    CASE WHEN aa.account_type = 'liability_payable'
                         THEN -aml.balance ELSE 0 END
                ), 0)  AS total_payable
            FROM account_move_line aml
            JOIN account_account aa
              ON aa.id = aml.account_id
            WHERE aa.account_type IN ('asset_receivable', 'liability_payable')
              AND aml.parent_state = 'posted'
              AND aml.company_id  = %s
              AND aml.date       <= %s::date
        """, (self.env.company.id, date_to))
        row = self.env.cr.dictfetchone()

        return {
            'total_receivable': row['total_receivable'],
            'total_payable':    row['total_payable'],
            'as_of':            date_to,
            'receivable_breakdown': self._partner_balance_breakdown(
                'asset_receivable', date_to, negate=False
            ),
            'payable_breakdown': self._partner_balance_breakdown(
                'liability_payable', date_to, negate=True
            ),
        }

    def _partner_balance_breakdown(self, account_type, date_to, negate=False):
        """Per-partner (or per-account, when no partner is set) open
        balance for one account type — just a name and a total, capped at
        15 rows for the modal, ordered by size. No due-date/aging logic.

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
              AND aml.reconciled  = false
            GROUP BY rp.id, rp.name, aa.id, aa.name
            HAVING COALESCE(SUM({sign} * aml.balance), 0) != 0
            ORDER BY total DESC
            LIMIT 15
        """, {
            'date_to':      date_to,
            'account_type': account_type,
            'company_id':   self.env.company.id,
            'lang':         lang,
        })
        return self.env.cr.dictfetchall()

    # ─────────────────────────────────────────────────────────────────────
    # CUSTOMER CREDIT  (from the optional 'customer_credit_report' module)
    # ─────────────────────────────────────────────────────────────────────
    def _get_customer_credit_data(self):
        """Outstanding customer credit summary for executives.

        Sourced from res.partner fields added by 'customer_credit_report'
        (x_total_sale_amount, x_total_invoiced, x_credit_amount_paid,
        x_remaining_balance) plus the native 'credit' field (Outstanding
        Credit). Those compute fields are not stored, so this is done via
        the ORM (not raw SQL) — the 'credit' field has a custom search
        method that still lets us filter server-side efficiently.

        Returns None if 'customer_credit_report' isn't installed, so the
        UI can hide the section instead of showing empty/zero data.
        """
        Partner = self.env['res.partner']
        if 'x_remaining_balance' not in Partner._fields:
            return None

        partners = Partner.search([
            ('customer_rank', '>', 0),
            ('credit', '>', 0.01),
        ])

        top = partners.sorted(key=lambda p: p.credit, reverse=True)[:10]
        top_customers = [{
            'customer':            p.name,
            'orders':              p.sale_order_count,
            'total_invoiced':      p.x_total_invoiced,
            'amount_paid':         p.x_credit_amount_paid,
            'outstanding_credit':  p.credit,
            'remaining_balance':   p.x_remaining_balance,
        } for p in top]

        return {
            'summary': {
                'customer_count':    len(partners),
                'total_outstanding': sum(partners.mapped('credit')),
                'total_invoiced':    sum(partners.mapped('x_total_invoiced')),
                'total_paid':        sum(partners.mapped('x_credit_amount_paid')),
            },
            'top_customers': top_customers,
        }

    # ─────────────────────────────────────────────────────────────────────
    # CUSTOMER DEPOSITS  (from the optional 'customer_deposit_credit' module)
    # ─────────────────────────────────────────────────────────────────────
    def _get_customer_deposit_data(self):
        """Customer deposit / advance-credit summary for executives.

        Sourced from res.partner fields added by 'customer_deposit_credit'
        (deposit_total_paid, deposit_total_invoiced, deposit_total_refunded,
        deposit_balance, is_deposit_customer). Those fields ARE stored, so
        we can search + order on them directly through the ORM.

        Returns None if 'customer_deposit_credit' isn't installed, so the
        UI can hide the section instead of showing empty/zero data.
        """
        Partner = self.env['res.partner']
        if 'deposit_balance' not in Partner._fields:
            return None

        partners = Partner.search(
            [('is_deposit_customer', '=', True)],
            order='deposit_balance desc',
        )
  
        top_customers = [{
            'customer':         p.name,
            'total_paid':       p.deposit_total_paid,
            'total_invoiced':   p.deposit_total_invoiced,
            'total_refunded':   p.deposit_total_refunded,
            'deposit_balance':  p.deposit_balance,
            'last_transaction': fields.Datetime.to_string(p.deposit_last_transaction_date)
                                 if p.deposit_last_transaction_date else False,
        } for p in partners[:10]]

        return {
            'summary': {
                'customer_count':  len(partners),
                'total_balance':   sum(partners.mapped('deposit_balance')),
                'total_paid':      sum(partners.mapped('deposit_total_paid')),
                'total_refunded':  sum(partners.mapped('deposit_total_refunded')),
            },
            'top_customers': top_customers,
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