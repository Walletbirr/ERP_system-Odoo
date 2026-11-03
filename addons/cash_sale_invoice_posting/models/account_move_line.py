from odoo import _, api, models
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends('move_id.x_is_cash_sale', 'move_id.x_cash_order_id')
    def _compute_account_id(self):
        super()._compute_account_id()
        for line in self:
            move = line.move_id
            if (line.display_type == 'payment_term'
                    and move.x_is_cash_sale
                    and move.move_type == 'out_invoice'
                    and move.state == 'draft'
                    and not getattr(move, 'manual_journal_items', False)):
                banks = move._cash_sale_approved_banks()
                if banks and banks[0][0].default_account_id:
                    line.account_id = banks[0][0].default_account_id

    @api.depends('move_id.x_is_cash_sale')
    def _compute_amount_residual(self):
        """A bank (cash) account normally keeps a residual equal to the line
        amount. On a cash sale invoice nothing is left to collect, so the
        bank line must never look open to the reconciliation tools."""
        super()._compute_amount_residual()
        for line in self:
            if (line.display_type == 'payment_term'
                    and line.move_id.x_is_cash_sale
                    and line.move_id.move_type == 'out_invoice'
                    and line.account_id.account_type not in (
                        'asset_receivable', 'liability_payable')):
                line.amount_residual = 0.0
                line.amount_residual_currency = 0.0

    @api.constrains('account_id', 'display_type')
    def _check_payable_receivable(self):
        """Odoo 18 forces every customer-invoice "payment term" line onto a
        receivable account ("Any journal item on a receivable account must
        have a due date and vice versa"). On a cash sale that line is the
        bank, so the rule is relaxed for those invoices only; every other
        invoice keeps the standard check."""
        cash = self.filtered(
            lambda l: l.move_id.x_is_cash_sale
            and l.move_id.move_type == 'out_invoice')
        super(AccountMoveLine, self - cash)._check_payable_receivable()
        for line in cash:
            account_type = line.account_id.account_type
            if account_type == 'liability_payable':
                raise UserError(_(
                    "Account %s is of payable type, but is used in a sale "
                    "operation.", line.account_id.code))
            # Any other account (the bank, the customer's own receivable
            # account as a credit OR a debit, income, expense...) is the
            # accountant's decision. The customer is filled in when the
            # invoice is posted, and 'debits = credits' is always checked.
