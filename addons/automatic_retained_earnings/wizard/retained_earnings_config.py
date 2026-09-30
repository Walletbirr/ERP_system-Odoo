# -*- coding: utf-8 -*-
"""
A small, self-contained configuration screen that lives entirely inside the
Accounting module, so the accounting team can set up Retained Earnings
closing themselves without needing Settings/Company-admin access.

Deliberately NOT built by inheriting res.config.settings: that mega-view is
heavily customised by some accounting kits (that's what broke the first
version of this module), so this is a plain, independent wizard instead -
much less likely to conflict with anything else installed.
"""
from odoo import api, fields, models


class AccountRetainedEarningsConfig(models.TransientModel):
    _name = 'account.retained.earnings.config'
    _description = 'Retained Earnings Setup (Accounting)'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    retained_earnings_account_id = fields.Many2one(
        'account.account', string='Retained Earnings Account', required=True,
        domain="[('account_type', '=', 'equity'), ('deprecated', '=', False)]",
        help="Equity account that receives the net profit/loss of every "
             "closed fiscal year.")
    closing_journal_id = fields.Many2one(
        'account.journal', string='Closing Journal', required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help="Miscellaneous/General journal used to post the year-end "
             "closing entry.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        res.update({
            'company_id': company.id,
            'retained_earnings_account_id': company.retained_earnings_account_id.id,
            'closing_journal_id': company.closing_journal_id.id,
        })
        return res

    def action_save(self):
        self.ensure_one()
        # sudo() because res.company write access is normally restricted to
        # Settings/Administration; Accounting Managers still shouldn't need
        # that access just to use this screen.
        self.company_id.sudo().write({
            'retained_earnings_account_id': self.retained_earnings_account_id.id,
            'closing_journal_id': self.closing_journal_id.id,
        })
        return {'type': 'ir.actions.act_window_close'}
