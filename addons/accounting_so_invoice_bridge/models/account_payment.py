from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import formatLang


class BridgePaymentBankLine(models.Model):
    """One bank / cash journal that received part of ONE customer payment.

    A payment with several of these is still a single account.payment with a
    single reference and a single journal entry: the entry has ONE receivable
    line (the full amount, reconciled with the invoice) and ONE debit line per
    bank row, each on the outstanding-receipts account of that bank's journal,
    so every bank statement can still be matched against its own line."""
    _name = 'bridge.payment.bank.line'
    _description = 'Payment - Bank Line'
    _order = 'sequence, id'

    payment_id = fields.Many2one(
        'account.payment', string='Payment', required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='payment_id.company_id', store=True, string='Company')
    sequence = fields.Integer(default=10)
    journal_id = fields.Many2one(
        'account.journal', string='Bank / Journal', required=True,
        domain="[('type', 'in', ('bank', 'cash'))]")
    currency_id = fields.Many2one(
        related='payment_id.currency_id', string='Currency')
    amount = fields.Monetary(
        string='Amount', required=True, currency_field='currency_id')

    @api.constrains('amount')
    def _check_amount_positive(self):
        for line in self:
            if line.currency_id.compare_amounts(line.amount, 0) <= 0:
                raise ValidationError(_(
                    "The amount received in %s must be greater than zero.",
                    line.journal_id.display_name))


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    bridge_bank_line_ids = fields.One2many(
        'bridge.payment.bank.line', 'payment_id', string='Banks', copy=False)
    bridge_is_multi_bank = fields.Boolean(
        compute='_compute_bridge_is_multi_bank',
        help="The money of this payment went into several banks.")
    bridge_bank_summary = fields.Char(
        string='Banks Summary', compute='_compute_bridge_bank_summary')

    @api.depends('bridge_bank_line_ids')
    def _compute_bridge_is_multi_bank(self):
        for pay in self:
            pay.bridge_is_multi_bank = len(pay.bridge_bank_line_ids) > 1

    @api.depends('bridge_bank_line_ids.amount',
                 'bridge_bank_line_ids.journal_id', 'currency_id')
    def _compute_bridge_bank_summary(self):
        for pay in self:
            banks = pay.bridge_bank_line_ids
            if len(banks) < 2:
                pay.bridge_bank_summary = False
                continue
            pay.bridge_bank_summary = ' + '.join(
                '%s %s' % (
                    bank.journal_id.name,
                    formatLang(self.env, bank.amount,
                               currency_obj=pay.currency_id))
                for bank in banks)

    # -------------------------------------------------------------------------
    # JOURNAL ENTRY: ONE RECEIVABLE LINE, ONE BANK LINE PER ROW
    # -------------------------------------------------------------------------

    def _bridge_outstanding_account(self, journal):
        """Outstanding receipts account for the money received in `journal`,
        found the same way Odoo finds it for a normal payment of that journal."""
        self.ensure_one()
        if journal == self.journal_id and self.outstanding_account_id:
            return self.outstanding_account_id
        method = self.payment_method_line_id.payment_method_id
        lines = journal.inbound_payment_method_line_ids
        line = lines.filtered(lambda l: l.payment_method_id == method)[:1] \
            or lines[:1]
        return line.payment_account_id \
            or self._get_outstanding_account(self.payment_type)

    def _get_valid_liquidity_accounts(self):
        """The bank lines of the other banks must be recognised as liquidity
        lines (not as write-off lines), or the payment would not know that
        they belong to it."""
        accounts = super()._get_valid_liquidity_accounts()
        for bank in self.bridge_bank_line_ids:
            journal = bank.journal_id
            accounts |= (
                journal.default_account_id
                | journal.inbound_payment_method_line_ids.payment_account_id)
            try:
                accounts |= self._bridge_outstanding_account(journal)
            except UserError:
                continue
        return accounts

    def _prepare_move_liquidity_lines(self, default_values):
        self.ensure_one()
        banks = self.bridge_bank_line_ids
        if len(banks) < 2 or self.payment_type != 'inbound':
            return super()._prepare_move_liquidity_lines(default_values)

        currency = self.currency_id
        if currency.compare_amounts(sum(banks.mapped('amount')), self.amount):
            raise UserError(_(
                "The amounts received in the banks (%(banks)s) must add up "
                "to the payment amount (%(amount)s).",
                banks=formatLang(self.env, sum(banks.mapped('amount')),
                                 currency_obj=currency),
                amount=formatLang(self.env, self.amount,
                                  currency_obj=currency)))

        template = super()._prepare_move_liquidity_lines(default_values)[0]
        company = self.company_id
        date = self.date or fields.Date.context_today(self)
        total_amount = default_values['amount_currency']
        total_balance = default_values['balance']
        # Anything Odoo took off the bank side (a withholding, for example)
        # is taken off the last bank, so the entry always balances.
        extra = total_amount - sum(banks.mapped('amount'))

        vals_list = []
        used_balance = 0.0
        last = len(banks) - 1
        for index, bank in enumerate(banks):
            amount_currency = bank.amount + (extra if index == last else 0.0)
            if index == last:
                balance = total_balance - used_balance
            else:
                balance = currency._convert(
                    amount_currency, company.currency_id, company, date)
                used_balance += balance
            vals = dict(template)
            vals.update({
                'name': ' - '.join(
                    x for x in (template.get('name'), bank.journal_id.name)
                    if x),
                'account_id': self._bridge_outstanding_account(
                    bank.journal_id).id,
                'amount_currency': amount_currency,
                'balance': balance,
            })
            vals_list.append(vals)
        return vals_list
