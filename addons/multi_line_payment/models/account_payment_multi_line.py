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
        string="Amount", currency_field='currency_id', required=True)

    @api.constrains('amount')
    def _check_amount_positive(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_("Each payment line amount must be greater than zero."))
