from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends('move_id.x_lc_id')
    def _compute_account_id(self):
        """Draft LC bill: the payment-term line sits on the LC's GIT
        account instead of the payable."""
        super()._compute_account_id()
        for line in self:
            move = line.move_id
            if (line.display_type == 'payment_term'
                    and move.move_type == 'in_invoice'
                    and move.state == 'draft'
                    and move.x_lc_id.opening_fee_account_id):
                line.account_id = move.x_lc_id.opening_fee_account_id

    @api.depends('move_id.x_is_lc_bill', 'move_id.state',
                 'move_id.x_lc_unsettled_amount', 'move_id.amount_total')
    def _compute_amount_residual(self):
        """What is still owed on an LC bill is what its confirmed LC
        settlements have not covered yet. The margin share counts as paid
        because the tranche amount includes it. Only the USD (bill
        currency) side drives this; the company-currency residual follows
        proportionally, so rate differences never leave a stray balance."""
        super()._compute_amount_residual()
        for line in self:
            move = line.move_id
            if not (move.x_is_lc_bill and move.state == 'posted'
                    and line.display_type == 'payment_term'):
                continue
            currency = move.currency_id
            total = move.amount_total
            unsettled = move.x_lc_unsettled_amount
            if currency.is_zero(unsettled):
                line.amount_residual = 0.0
                line.amount_residual_currency = 0.0
            elif currency.is_zero(total) or unsettled >= total:
                line.amount_residual = line.balance
                line.amount_residual_currency = line.amount_currency
            else:
                ratio = unsettled / total
                line.amount_residual = line.company_currency_id.round(
                    line.balance * ratio)
                line.amount_residual_currency = currency.round(
                    line.amount_currency * ratio)

    @api.constrains('account_id', 'display_type')
    def _check_payable_receivable(self):
        """Odoo requires a payable account on a vendor bill's payment-term
        line. On an LC bill that line is the LC's GIT account, so the rule
        is relaxed for those lines only."""
        lc_lines = self.filtered(
            lambda l: l.display_type == 'payment_term'
            and l.move_id.move_type == 'in_invoice'
            and l.move_id.x_lc_id
            and l.account_id == l.move_id.x_lc_id.opening_fee_account_id)
        super(AccountMoveLine, self - lc_lines)._check_payable_receivable()
