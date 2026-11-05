from datetime import date as Date

from odoo import _, fields, models
from odoo.tools import float_is_zero

from .credit_line import (ACCOUNT_LINE_FREE_SQL, ACCOUNT_LINE_NOT_DOC_SQL,
                          PREVIOUS_BALANCE_SQL)

# How a statement entry is shown.
ENTRY_LABELS = {
    'invoice': 'Credit Invoice',
    'credit_note': 'Credit Note',
    'payment': 'Payment',
    'refund_payment': 'Refund Paid Out',
    'other': 'Adjustment',
    'previous': 'Previous Balance',
    'previous_payment': 'Payment',
}


class CustomerCreditStatement(models.AbstractModel):
    """Customer statement for credit sales.

    Debit  = credit invoices (credit notes as negative debits).
    Credit = amounts matched to those documents from outside them
             (payments, write-offs...). A credit note matched to a credit
             invoice is already counted as a document, so it is not
             counted again.
    The closing balance therefore always equals the sum of the unpaid
    parts of the credit invoices (the Remaining of the credit report).
    """
    _name = 'customer.credit.statement'
    _description = 'Customer Credit Statement'

    def _previous_entries(self, partner, company):
        """Customers with their own Credit Account: one Previous Balance
        entry (everything on the account up to the day of their first
        credit sale in Odoo, dated by its last entry), then every later
        movement on the account that is not about a credit sale (payments
        of the previous balance, adjustments)."""
        cr = self.env.cr
        cr.execute(f"""
            SELECT boundary, prev_start, account_id, prev_date
              FROM ({PREVIOUS_BALANCE_SQL}) pb
             WHERE pb.partner_id = %s AND pb.company_id = %s
        """, (partner.id, company.id))
        row = cr.fetchone()
        if not row:
            return []
        boundary, prev_start, account_id, prev_date = row
        rounding = company.currency_id.rounding
        entries = []
        if not float_is_zero(prev_start, precision_rounding=rounding):
            entries.append({
                'kind': 'previous',
                'date': prev_date or fields.Date.context_today(self),
                'move_id': False,
                'doc_id': False,
                'amount': prev_start,
                'seq': -1,
            })
        if not boundary:
            return entries
        cr.execute(f"""
            SELECT aml.date, aml.move_id, aml.name, {ACCOUNT_LINE_FREE_SQL}
              FROM account_move_line aml
             WHERE aml.account_id = %s
               AND aml.company_id = %s
               AND aml.parent_state = 'posted'
               AND aml.date > %s
               AND {ACCOUNT_LINE_NOT_DOC_SQL}
        """, (account_id, company.id, boundary))
        rows = [r for r in cr.fetchall()
                if not float_is_zero(r[3], precision_rounding=rounding)]
        moves = self.env['account.move'].sudo().browse({r[1] for r in rows})
        payment_moves = set(self.env['account.payment'].sudo().search(
            [('move_id', 'in', moves.ids)]).mapped('move_id').ids)
        for line_date, move_id, label, amount in rows:
            if move_id in payment_moves:
                kind = 'previous_payment' if amount < 0 else 'refund_payment'
            else:
                kind = 'other'
            entries.append({
                'kind': kind,
                'date': line_date,
                'move_id': move_id,
                'doc_id': False,
                'amount': amount,
                'seq': 1,
                'label': label,
            })
        return entries

    def _statement_entries(self, partner, company):
        self.env.flush_all()
        cr = self.env.cr
        entries = self._previous_entries(partner, company)
        params = {'partner': partner.id, 'company': company.id}
        cr.execute("""
            SELECT am.id, am.move_type, am.invoice_date,
                   am.amount_total_signed
              FROM account_move am
             WHERE am.move_type IN ('out_invoice', 'out_refund')
               AND am.state = 'posted'
               AND am.x_sale_type = 'credit'
               AND am.commercial_partner_id = %(partner)s
               AND am.company_id = %(company)s
        """, params)
        docs = cr.fetchall()
        for move_id, move_type, inv_date, amount in docs:
            entries.append({
                'kind': 'invoice' if move_type == 'out_invoice'
                else 'credit_note',
                'date': inv_date,
                'move_id': move_id,
                'doc_id': move_id,
                'amount': amount,  # + increases what the customer owes
                'seq': 0,
            })
        if not docs:
            return entries

        cr.execute("""
            WITH doc_lines AS (
                SELECT aml.id
                  FROM account_move_line aml
                  JOIN account_account aa ON aa.id = aml.account_id
                 WHERE aml.move_id = ANY(%(docs)s)
                   AND aa.account_type = 'asset_receivable'
            )
            -- something paid a credit invoice
            SELECT apr.id, -apr.amount, cl.date, cl.move_id, dl.move_id,
                   'in'
              FROM account_partial_reconcile apr
              JOIN account_move_line dl ON dl.id = apr.debit_move_id
              JOIN account_move_line cl ON cl.id = apr.credit_move_id
             WHERE apr.debit_move_id IN (SELECT id FROM doc_lines)
               AND apr.credit_move_id NOT IN (SELECT id FROM doc_lines)
            UNION ALL
            -- a credit note was paid out / used outside credit invoices
            SELECT apr.id, apr.amount, dl.date, dl.move_id, cl.move_id,
                   'out'
              FROM account_partial_reconcile apr
              JOIN account_move_line dl ON dl.id = apr.debit_move_id
              JOIN account_move_line cl ON cl.id = apr.credit_move_id
             WHERE apr.credit_move_id IN (SELECT id FROM doc_lines)
               AND apr.debit_move_id NOT IN (SELECT id FROM doc_lines)
        """, {'docs': [d[0] for d in docs]})
        rows = cr.fetchall()
        other_moves = self.env['account.move'].browse(
            {r[3] for r in rows}).sudo()
        paying = {m.id: m for m in other_moves}
        payment_moves = set(self.env['account.payment'].sudo().search(
            [('move_id', 'in', other_moves.ids)]).mapped('move_id').ids)
        for apr_id, amount, pdate, other_id, doc_id, direction in rows:
            if other_id in payment_moves:
                kind = 'payment' if direction == 'in' else 'refund_payment'
            else:
                kind = 'other'
            entries.append({
                'kind': kind,
                'date': pdate,
                'move_id': other_id,
                'doc_id': doc_id,
                'amount': amount,
                'seq': 1,
                'partial_id': apr_id,
                'journal': paying[other_id].journal_id.name,
            })
        return entries

    def _get_statement(self, partner, company, date_from=None, date_to=None):
        partner = partner.commercial_partner_id
        currency = company.currency_id
        date_to = date_to or fields.Date.context_today(self)
        entries = self._statement_entries(partner, company)
        entries.sort(key=lambda e: (e['date'] or Date.min, e['seq'],
                                    e['move_id'] or 0))
        if not date_from:
            dates = [e['date'] for e in entries if e['date']]
            date_from = min(dates) if dates else date_to

        Move = self.env['account.move'].sudo()
        moves = Move.browse(({e['move_id'] for e in entries}
                             | {e['doc_id'] for e in entries}) - {False})
        by_id = {m.id: m for m in moves}

        opening = 0.0
        balance = 0.0
        lines = []
        total_debit = total_credit = 0.0
        for e in entries:
            if e['date'] and e['date'] < date_from:
                opening += e['amount']
                continue
            if e['date'] and e['date'] > date_to:
                continue
            if not lines:
                balance = opening
            move = by_id.get(e['move_id'], Move)
            doc = by_id.get(e['doc_id'], Move)
            debit = e['amount'] if e['amount'] > 0 else 0.0
            credit = -e['amount'] if e['amount'] < 0 else 0.0
            balance += e['amount']
            total_debit += debit
            total_credit += credit
            if e['kind'] == 'previous':
                description = (
                    _('Owed before the first credit sale in Odoo')
                    if e['amount'] > 0 else
                    _("In the customer's favour before the first credit sale "
                      "in Odoo (deposits / advances)"))
                due = False
            elif e['kind'] == 'previous_payment' or (
                    e['kind'] in ('other', 'refund_payment') and not doc):
                description = (
                    _('%s — for the previous balance', move.journal_id.name)
                    if e['kind'] == 'previous_payment'
                    else (move.ref or e.get('label') or move.journal_id.name
                          or ''))
                memo = move.ref or ''
                if e['kind'] == 'previous_payment' and memo:
                    description = '%s (%s)' % (description, memo)
                due = False
            elif e['kind'] in ('invoice', 'credit_note'):
                description = move.invoice_origin or move.ref or ''
                if e['kind'] == 'credit_note' and move.reversed_entry_id:
                    description = _('Reverses %s',
                                    move.reversed_entry_id.name)
                due = move.invoice_date_due if e['kind'] == 'invoice' \
                    else False
            else:
                memo = move.ref or ''
                description = _('%(journal)s — for %(doc)s',
                                journal=e.get('journal') or '',
                                doc=doc.name)
                if memo and memo != doc.name:
                    description = '%s (%s)' % (description, memo)
                due = False
            lines.append({
                'date': e['date'],
                'kind': e['kind'],
                'kind_label': _(ENTRY_LABELS[e['kind']]),
                'reference': move.name or _('Previous balance'),
                'description': description,
                'date_due': due,
                'debit': debit,
                'credit': credit,
                'balance': balance,
                'move_id': move.id,
            })
        if not lines:
            balance = opening
        closing = balance

        position = self.env['customer.credit.summary'].sudo()._position(
            partner, company)
        self.env['customer.credit.line'].invalidate_model()
        open_lines = self.env['customer.credit.line'].sudo().search([
            ('partner_id', '=', partner.id),
            ('company_id', '=', company.id),
            ('is_open', '=', True),
        ], order='date_due asc, id asc')
        return {
            'partner': partner,
            'company': company,
            'currency': currency,
            'date_from': date_from,
            'date_to': date_to,
            'today': fields.Date.context_today(self),
            'opening': opening,
            'lines': lines,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'closing': closing,
            'position': position,
            'open_lines': open_lines,
            'is_current': date_to >= fields.Date.context_today(self),
            'is_zero': lambda amount: float_is_zero(
                amount, precision_rounding=currency.rounding),
        }
