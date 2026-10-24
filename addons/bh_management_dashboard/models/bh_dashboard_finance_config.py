# -*- coding: utf-8 -*-
from odoo import models


class BhManagementDashboardFinanceConfig(models.Model):
    """Makes the Finance cards honour Configuration > Finance Accounts.

    Each override first checks whether anything is configured; if not, it
    calls super() so the original behaviour (by account type / by journal)
    is untouched.
    """
    _inherit = 'bh.management.dashboard'

    # ------------------------------------------------------------------
    def _finance_config(self):
        """The current company's config, or an empty recordset. Read-only
        (never creates a record while the dashboard is just being read)."""
        return self.env['bh.dashboard.config'].sudo().search(
            [('company_id', '=', self.env.company.id)], limit=1)

    def _finance_account_ids(self, configured, account_type):
        """Configured accounts, or - for a list left empty - every account
        of the original type."""
        if configured:
            return list(configured.ids)
        return self.env['account.account'].sudo().search(
            [('account_type', '=', account_type)]).ids

    # ------------------------------------------------------------------
    # Receivable / Payable
    # ------------------------------------------------------------------
    def _get_receivable_payable_data(self, date_to):
        """Receivables / Payables from the accounts picked in
        Configuration > Finance Accounts - and nothing else.

        A list left empty is NOT "all accounts of that type": that card is
        reported as not configured (total None, empty break-down) so the app
        shows "Not set up" instead of a number nobody chose."""
        cfg = self._finance_config()
        rec_ids = cfg.receivable_account_ids.ids if cfg else []
        # an account is never counted on both sides
        pay_ids = [i for i in (cfg.payable_account_ids.ids if cfg else [])
                   if i not in set(rec_ids)]

        # One balance PER ACCOUNT (debits and credits of every contact on it
        # netted together, exactly the balance Odoo shows on the account):
        #   Receivable account: debit balance  = owed to us      (counted)
        #   Payable account   : credit balance = we owe          (counted)
        # An account on the other side (already paid / overpaid) is simply
        # not shown - it is never netted against the others.
        rec_rows = self._account_balance_breakdown(rec_ids, date_to, negate=False)
        pay_rows = self._account_balance_breakdown(pay_ids, date_to, negate=True)

        return {
            'total_receivable':  sum(r['total'] for r in rec_rows) if rec_ids else None,
            'total_payable':     sum(r['total'] for r in pay_rows) if pay_ids else None,
            'unapplied_credits': 0.0,
            'unapplied_debits':  0.0,
            'receivable_configured': bool(rec_ids),
            'payable_configured':    bool(pay_ids),
            'as_of':             date_to,
            'receivable_breakdown': rec_rows,
            'payable_breakdown': pay_rows,
        }

    def _account_balance_breakdown(self, account_ids, date_to, negate=False):
        """[{'partner_name': <account name>, 'total': amount owed}] - one row
        per account whose net balance (posted, up to date_to) is on the
        "owed" side, biggest first. `partner_name` keeps the key the app
        already reads."""
        if not account_ids:
            return []
        self.env.cr.execute("""
            SELECT aml.account_id, COALESCE(SUM(aml.balance), 0)
              FROM account_move_line aml
             WHERE aml.account_id = ANY(%s::int[])
               AND aml.parent_state = 'posted'
               AND aml.company_id  = %s
               AND aml.date       <= %s::date
             GROUP BY aml.account_id
        """, (account_ids, self.env.company.id, date_to))
        balances = dict(self.env.cr.fetchall())   # read NOW, ORM reads below reuse the cursor
        sign = -1.0 if negate else 1.0
        accounts = self.env['account.account'].sudo().with_company(
            self.env.company).browse(list(balances))
        rows = []
        for acc in accounts:
            amount = sign * balances.get(acc.id, 0.0)
            if amount > 0.005:
                rows.append({'partner_name': self._clean_account_name(acc.name),
                             'total': amount})
        rows.sort(key=lambda r: r['total'], reverse=True)
        return rows

    def _partner_balance_breakdown_by_ids(self, account_ids, date_to, negate=False):
        """Same as _partner_balance_breakdown (per partner, or per account
        when a line has no partner; only positive amounts owed) but for an
        explicit list of accounts instead of one account type."""
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
            WHERE aml.account_id = ANY(%(ids)s::int[])
              AND aml.parent_state = 'posted'
              AND aml.company_id  = %(company_id)s
              AND aml.date       <= %(date_to)s::date
            GROUP BY rp.id, rp.name, aa.id, aa.name
            HAVING COALESCE(SUM({sign} * aml.balance), 0) > 0
            ORDER BY total DESC
            LIMIT 500
        """, {
            'date_to':    date_to,
            'ids':        account_ids,
            'company_id': self.env.company.id,
            'lang':       lang,
        })
        return self.env.cr.dictfetchall()

    # ------------------------------------------------------------------
    # Cash at Bank
    # ------------------------------------------------------------------
    def _get_cash_at_bank_data(self, date_to):
        cfg = self._finance_config()
        if not cfg or not cfg.cash_account_ids:
            # Nothing picked in the configuration: no number (never "every
            # Bank and Cash journal").
            return {'total_balance': None, 'bank_count': 0, 'as_of': date_to,
                    'banks': [], 'configured': False}

        account_ids = cfg.cash_account_ids.ids
        self.env.cr.execute("""
            SELECT aml.account_id, COALESCE(SUM(aml.balance), 0) AS balance
            FROM account_move_line aml
            WHERE aml.account_id = ANY(%s::int[])
              AND aml.parent_state = 'posted'
              AND aml.company_id  = %s
              AND aml.date       <= %s::date
            GROUP BY aml.account_id
        """, (account_ids, self.env.company.id, date_to))
        balances = dict(self.env.cr.fetchall())

        accounts = self.env['account.account'].sudo().with_company(
            self.env.company).browse(account_ids)
        banks = [{
            'id':             account.id,
            'name':           account.name,
            'type':           'bank',
            'account_number': account.code,
            'bank_provider':  None,
            'balance':        balances.get(account.id, 0.0),
        } for account in accounts]
        banks.sort(key=lambda b: b['balance'], reverse=True)

        return {
            'total_balance': sum(b['balance'] for b in banks),
            'bank_count':    len(banks),
            'as_of':         date_to,
            'banks':         banks,
            'configured':    True,
        }