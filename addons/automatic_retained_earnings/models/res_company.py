# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    retained_earnings_account_id = fields.Many2one(
        'account.account',
        string='Retained Earnings Account',
        domain="[('account_type', '=', 'equity'), ('deprecated', '=', False)]",
        help="Equity account that accumulates the net profit or loss of "
             "every closed fiscal year. Every Income/Expense account is "
             "reset to zero into this account when a fiscal year is closed."
    )
    closing_journal_id = fields.Many2one(
        'account.journal',
        string='Closing Entries Journal',
        domain="[('type', '=', 'general')]",
        help="Miscellaneous/General journal used to post the automatic "
             "year-end closing entries. Defaults to the first Miscellaneous "
             "Operations journal found for the company if left empty."
    )
    auto_close_fiscalyear = fields.Boolean(
        string='Auto-Post Closing Entry',
        help="If enabled, a daily scheduled action will automatically "
             "generate and post the retained earnings closing entry on "
             "the configured Auto-Post Date each year, provided a "
             "Retained Earnings account is configured. Most companies "
             "should leave this off and close manually from "
             "Accounting > Fiscal Year Closing instead."
    )
    auto_close_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='Auto-Post Month', default='1',
        help="Month of the Auto-Post Date: the calendar day each year on "
             "which the closing entry for the most recently completed "
             "fiscal year is generated and posted automatically.")
    auto_close_day = fields.Integer(
        string='Auto-Post Day', default=1,
        help="Day of the month of the Auto-Post Date (1-31). If the month "
             "has fewer days, the last day of that month is used instead. "
             "Set this a few days/weeks after your fiscal year end if you "
             "want a grace period for late entries before auto-closing.")
