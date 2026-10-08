# -*- coding: utf-8 -*-
import re

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
        string="Amount", currency_field='currency_id', required=True,
        help="Enter a positive amount for the normal side (Payment Voucher: "
             "debit, Receipt Voucher: credit). Enter a negative amount to put "
             "the line on the opposite side.")

    is_tax = fields.Boolean(
        string="Tax", compute='_compute_is_tax',
        help="Tax / VAT lines are posted on the entry but are not part of the "
             "payment Amount. Worked out from the account: used by a tax, or "
             "its name has a tax word (VAT, tax, withholding...).")

    @api.model
    def _get_tax_name_pattern(self):
        """ Whole words in the account NAME that mark a tax account, e.g. the
        "VAT" in "2400-01 VAT REC/PAY". Whole words only, so "Taxi" does not
        match. Change in System Parameters:
        multi_line_payment.tax_account_keywords (comma separated). """
        value = self.env['ir.config_parameter'].sudo().get_param(
            'multi_line_payment.tax_account_keywords',
            'vat,tax,taxes,wht,withholding')
        words = [re.escape(w.strip()) for w in (value or '').split(',') if w.strip()]
        if not words:
            return None
        return re.compile(r'\b(?:%s)\b' % '|'.join(words), re.IGNORECASE)

    @api.depends('account_id')
    def _compute_is_tax(self):
        tax_accounts = self.env['account.tax.repartition.line'].sudo().search(
            [('account_id', '!=', False)]).mapped('account_id')
        pattern = self._get_tax_name_pattern()
        for line in self:
            account = line.account_id
            line.is_tax = bool(account) and (
                account in tax_accounts
                or bool(pattern and pattern.search(account.name or '')))

    @api.constrains('amount')
    def _check_amount_not_zero(self):
        for line in self:
            if line.currency_id.is_zero(line.amount):
                raise ValidationError(_("A payment line amount cannot be zero."))
