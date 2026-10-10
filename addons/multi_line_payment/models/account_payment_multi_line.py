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

    exclude_from_amount = fields.Boolean(
        string="Exclude", compute='_compute_exclude_from_amount',
        store=True, readonly=False,
        help="Ticked lines (tax / VAT / withholding) are posted on the entry "
             "but are not counted in the payment Amount. Ticked automatically "
             "from the account, and you can change it on the line.")

    @api.model
    def _get_exclude_pattern(self):
        """ Words in the account NAME that suggest the line is not part of the
        paid expense (tax, VAT, withholding). Whole words, plural
        accepted. Change in System Parameters:
        multi_line_payment.exclude_keywords (comma separated). """
        value = self.env['ir.config_parameter'].sudo().get_param(
            'multi_line_payment.exclude_keywords',
            'vat,tax,wht,withholding')
        words = []
        for w in (value or '').split(','):
            parts = w.split()
            if parts:
                words.append(r'\s+'.join(re.escape(x) for x in parts))
        if not words:
            return None
        return re.compile(r'\b(?:%s)(?:e?s)?\b' % '|'.join(words), re.IGNORECASE)

    @api.depends('account_id')
    def _compute_exclude_from_amount(self):
        tax_accounts = self.env['account.tax.repartition.line'].sudo().search(
            [('account_id', '!=', False)]).mapped('account_id')
        pattern = self._get_exclude_pattern()
        for line in self:
            account = line.account_id
            line.exclude_from_amount = bool(account) and (
                account in tax_accounts
                or bool(pattern and pattern.search(account.name or '')))

    @api.constrains('amount')
    def _check_amount_not_zero(self):
        for line in self:
            if line.currency_id.is_zero(line.amount):
                raise ValidationError(_("A payment line amount cannot be zero."))
