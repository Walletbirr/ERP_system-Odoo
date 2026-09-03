# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LeaveTaxBracket(models.Model):
    _name = 'leave.tax.bracket'
    _description = 'Income Tax Bracket (used to auto-select the encashment tax rate)'
    _order = 'min_amount'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    name = fields.Char(compute='_compute_name')
    min_amount = fields.Monetary(required=True)
    max_amount = fields.Monetary(
        help="Leave at 0 for 'and above' (no upper limit) - the top bracket.")
    rate = fields.Float(string="Rate (%)", required=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    @api.depends('min_amount', 'max_amount', 'rate')
    def _compute_name(self):
        for rec in self:
            if rec.max_amount:
                rec.name = f"{rec.min_amount:,.0f} - {rec.max_amount:,.0f} -> {rec.rate:.0f}%"
            else:
                rec.name = f"Above {rec.min_amount:,.0f} -> {rec.rate:.0f}%"

    @api.model
    def _get_rate_for_amount(self, amount, company=None):
        """Returns the rate (%) of the bracket that `amount` falls into, checked
        against this company's bracket table. Brackets are read low-to-high; the
        first one whose range contains `amount` wins. Returns 0.0 if no bracket
        matches (e.g. no brackets configured) - callers should treat that as
        'unconfigured', not 'zero tax due'."""
        company = company or self.env.company
        brackets = self.search([('company_id', '=', company.id)], order='min_amount')
        for b in brackets:
            if amount >= b.min_amount and (not b.max_amount or amount <= b.max_amount):
                return b.rate
        return 0.0
