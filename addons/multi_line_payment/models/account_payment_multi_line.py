# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountPaymentMultiLine(models.Model):
    _name = 'account.payment.multi.line'
    _description = 'Payment Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    payment_id = fields.Many2one(
        'account.payment', string="Payment", required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='payment_id.company_id', store=True, string="Company")
    currency_id = fields.Many2one(
        related='payment_id.currency_id', string="Currency")
    account_id = fields.Many2one(
        'account.account', string="Account", required=True,
        domain="[('deprecated', '=', False)]")
    partner_id = fields.Many2one('res.partner', string="Partner")
    name = fields.Char(string="Description")
    amount = fields.Monetary(
        string="Amount", currency_field='currency_id', required=True, default=0.0,
        help="Enter a positive amount for the normal side (Payment Voucher: "
             "debit, Receipt Voucher: credit). Enter a negative amount to put "
             "the line on the opposite side.")

    exclude_from_amount = fields.Boolean(
        string="Exclude", default=False,
        help="Ticked lines (tax / VAT / withholding) are posted on the entry "
             "but are not counted in the payment Amount. Nothing is ticked "
             "automatically: the user chooses on each line.")

    @api.constrains('amount')
    def _check_amount_not_zero(self):
        for line in self.filtered(lambda l: not l.payment_id.is_void):
            if line.currency_id.is_zero(line.amount):
                raise ValidationError(_("A payment line amount cannot be zero."))
