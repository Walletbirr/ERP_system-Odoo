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
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
    auto_close_fiscalyear = fields.Boolean(
        string='Auto-Post Closing Entry Every Year',
        help="If enabled, the closing entry is generated and posted "
             "automatically on the Auto-Post Date below each year. If "
             "disabled (recommended for most companies), accountants "
             "close each year manually from Fiscal Year Closing.")
    auto_close_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='Auto-Post Month')
    auto_close_day = fields.Integer(
        string='Auto-Post Day',
        help="Day of the month (1-31) on which the automatic closing "
             "runs each year, together with Auto-Post Month. Set this a "
             "few days or weeks after your fiscal year end if you want a "
             "grace period for late entries before auto-closing.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        res.update({
            'company_id': company.id,
            'retained_earnings_account_id': company.retained_earnings_account_id.id,
            'closing_journal_id': company.closing_journal_id.id,
            'auto_close_fiscalyear': company.auto_close_fiscalyear,
            'auto_close_month': company.auto_close_month or '1',
            'auto_close_day': company.auto_close_day or 1,
        })
        return res

    @api.constrains('auto_close_fiscalyear', 'auto_close_month', 'auto_close_day')
    def _check_auto_close_date(self):
        for rec in self:
            if rec.auto_close_fiscalyear:
                if not rec.auto_close_month or not rec.auto_close_day:
                    raise ValidationError(_(
                        'Please set the Auto-Post Month and Day before enabling '
                        'automatic yearly closing.'))
                if not (1 <= rec.auto_close_day <= 31):
                    raise ValidationError(_('Auto-Post Day must be between 1 and 31.'))

    def action_save(self):
        self.ensure_one()
        # sudo() because res.company write access is normally restricted to
        # Settings/Administration; Accounting Managers still shouldn't need
        # that access just to use this screen.
        self.company_id.sudo().write({
            'retained_earnings_account_id': self.retained_earnings_account_id.id,
            'closing_journal_id': self.closing_journal_id.id,
            'auto_close_fiscalyear': self.auto_close_fiscalyear,
            'auto_close_month': self.auto_close_month,
            'auto_close_day': self.auto_close_day,
        })
        return {'type': 'ir.actions.act_window_close'}
