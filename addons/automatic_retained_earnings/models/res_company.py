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
