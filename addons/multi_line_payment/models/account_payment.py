# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # Accounting voucher names: Send = CPV, Receive = CRV
    payment_type = fields.Selection(
        selection=[
            ('outbound', 'Cash Payment Voucher (CPV)'),
            ('inbound', 'Cash Receipt Voucher (CRV)'),
        ])

    is_multi_line = fields.Boolean(string="Multiple Lines", copy=True)
    multi_line_ids = fields.One2many(
        'account.payment.multi.line', 'payment_id',
        string="Payment Lines", copy=True)

    # -------------------------------------------------------------------------
    # AMOUNT = TOTAL OF THE LINES
    # -------------------------------------------------------------------------

    @api.onchange('multi_line_ids', 'is_multi_line')
    def _onchange_multi_line_ids(self):
        for pay in self:
            if pay.is_multi_line:
                pay.amount = sum(pay.multi_line_ids.mapped('amount'))

    def _sync_multi_line_amount(self):
        """ The amount field is read-only in the form (so the browser does not
        send it back): always rebuild it from the lines on the server. """
        for pay in self.filtered('is_multi_line'):
            total = sum(pay.multi_line_ids.mapped('amount'))
            if pay.currency_id.compare_amounts(pay.amount, total) != 0:
                pay.with_context(skip_multi_line_amount_sync=True).write({'amount': total})

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        payments._sync_multi_line_amount()
        return payments

    def write(self, vals):
        res = super().write(vals)
        if (
            not self.env.context.get('skip_multi_line_amount_sync')
            and ('multi_line_ids' in vals or 'is_multi_line' in vals)
        ):
            self._sync_multi_line_amount()
        return res

    # -------------------------------------------------------------------------
    # JOURNAL ENTRY LINES
    # -------------------------------------------------------------------------

    def _prepare_multi_line_vals(self):
        """ One journal item per payment line, on the opposite side of the
        bank line (send: debit the lines, receive: credit the lines). """
        self.ensure_one()
        sign = 1 if self.payment_type == 'outbound' else -1
        company = self.company_id
        date = self.date or fields.Date.context_today(self)
        vals_list = []
        for line in self.multi_line_ids:
            amount_currency = sign * line.amount
            balance = self.currency_id._convert(
                amount_currency, company.currency_id, company, date)
            vals_list.append({
                'name': line.name or False,
                'date_maturity': date,
                'amount_currency': amount_currency,
                'currency_id': self.currency_id.id,
                'balance': balance,
                'partner_id': (line.partner_id or self.partner_id).id,
                'account_id': line.account_id.id,
            })
        return vals_list

    def _prepare_move_lines_per_type(self, write_off_line_vals=None, force_balance=None):
        res = super()._prepare_move_lines_per_type(
            write_off_line_vals=write_off_line_vals, force_balance=force_balance)
        self.ensure_one()
        if self.is_multi_line and self.multi_line_ids:
            # Bank side: always the bank / cash account set on the journal.
            bank_account = self.journal_id.default_account_id
            if not bank_account:
                raise UserError(_(
                    "The journal %s has no default account. Set the bank account "
                    "on the journal first.", self.journal_id.display_name))
            for liquidity_vals in res.get('liquidity_lines', []):
                liquidity_vals['account_id'] = bank_account.id
            res['counterpart_lines'] = self._prepare_multi_line_vals()
            res['write_off_lines'] = []
        return res

    # -------------------------------------------------------------------------
    # SYNCHRONIZATION WITH THE JOURNAL ENTRY
    # -------------------------------------------------------------------------

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        return super()._get_trigger_fields_to_synchronize() + (
            'is_multi_line', 'multi_line_ids')

    def _synchronize_to_moves(self, changed_fields):
        multi = self.filtered(lambda p: p.is_multi_line and p.multi_line_ids)
        super(AccountPayment, self - multi)._synchronize_to_moves(changed_fields)
        if not multi:
            return
        if not any(f in changed_fields for f in self._get_trigger_fields_to_synchronize()):
            return
        for pay in multi:
            # No entry yet (draft): it is generated on Confirm.
            if not pay.move_id or pay.move_id.state == 'posted':
                continue
            line_vals = pay._prepare_move_line_default_vals()
            to_write = {
                'date': pay.date,
                'partner_id': pay.partner_id.id,
                'currency_id': pay.currency_id.id,
                'partner_bank_id': pay.partner_bank_id.id,
                'line_ids': [Command.clear()] + [Command.create(v) for v in line_vals],
            }
            if 'journal_id' in changed_fields:
                to_write.update({'name': '/', 'journal_id': pay.journal_id.id})
            pay.move_id.with_context(skip_invoice_sync=True).write(to_write)

    def _synchronize_from_moves(self, changed_fields):
        multi = self.filtered(lambda p: p.is_multi_line and p.multi_line_ids)
        return super(AccountPayment, self - multi)._synchronize_from_moves(changed_fields)

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def action_post(self):
        multi = self.filtered('is_multi_line')
        for pay in multi:
            if not pay.multi_line_ids:
                raise UserError(_("Add at least one payment line before confirming."))
            pay._sync_multi_line_amount()
        res = super().action_post()
        # The bank side is posted straight to the journal's bank account (no
        # outstanding account), so there is nothing left to reconcile: the
        # payment is Paid as soon as it is confirmed.
        to_paid = multi.filtered(
            lambda p: p.move_id
            and p.state == 'in_process'
            and not p.journal_id.default_account_id.reconcile)
        if to_paid:
            to_paid.write({'state': 'paid'})
        return res
