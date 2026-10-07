# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountPaymentPostPreview(models.TransientModel):
    """ Confirmation window shown on Confirm: the journal items that will be
    posted, and nothing is posted until the user agrees. """
    _name = 'account.payment.post.preview'
    _description = 'Payment Journal Entry Confirmation'

    payment_id = fields.Many2one(
        'account.payment', required=True, readonly=True, ondelete='cascade')
    payment_type = fields.Selection(related='payment_id.payment_type')
    journal_id = fields.Many2one(related='payment_id.journal_id')
    partner_id = fields.Many2one(related='payment_id.partner_id')
    date = fields.Date(related='payment_id.date')
    memo = fields.Char(related='payment_id.memo')
    voucher_reference = fields.Char(related='payment_id.voucher_reference')
    company_currency_id = fields.Many2one(
        related='payment_id.company_id.currency_id')
    line_ids = fields.One2many(
        'account.payment.post.preview.line', 'preview_id', readonly=True)
    total_debit = fields.Monetary(
        compute='_compute_totals', currency_field='company_currency_id')
    total_credit = fields.Monetary(
        compute='_compute_totals', currency_field='company_currency_id')
    is_balanced = fields.Boolean(compute='_compute_totals')

    @api.depends('line_ids.debit', 'line_ids.credit', 'company_currency_id')
    def _compute_totals(self):
        for wiz in self:
            wiz.total_debit = sum(wiz.line_ids.mapped('debit'))
            wiz.total_credit = sum(wiz.line_ids.mapped('credit'))
            currency = wiz.company_currency_id
            wiz.is_balanced = (
                not currency
                or currency.compare_amounts(wiz.total_debit, wiz.total_credit) == 0)

    def action_confirm_post(self):
        self.ensure_one()
        self.payment_id.action_post()
        return {'type': 'ir.actions.act_window_close'}


class AccountPaymentPostPreviewLine(models.TransientModel):
    _name = 'account.payment.post.preview.line'
    _description = 'Payment Journal Entry Confirmation Line'
    _order = 'sequence, id'

    preview_id = fields.Many2one(
        'account.payment.post.preview', required=True, ondelete='cascade')
    sequence = fields.Integer()
    company_currency_id = fields.Many2one('res.currency')
    account_id = fields.Many2one('account.account', string="Account")
    partner_id = fields.Many2one('res.partner', string="Partner")
    name = fields.Char(string="Description")
    debit = fields.Monetary(currency_field='company_currency_id')
    credit = fields.Monetary(currency_field='company_currency_id')
