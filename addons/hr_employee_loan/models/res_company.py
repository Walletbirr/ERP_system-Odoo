# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    loan_account_id = fields.Many2one(
        'account.account', string='Employee Loan Account',
        domain="[('account_type', 'in', ('asset_current', 'asset_receivable', 'asset_non_current'))]",
        help="Default asset account that holds what employees still owe "
             "(Employee Loans Receivable).")
    loan_journal_id = fields.Many2one(
        'account.journal', string='Loan Disbursement Journal',
        help="Default journal used to pay out loans (bank / cash).")
    loan_deduction_paused = fields.Boolean(
        string='Pause All Loan Deductions', default=False,
        help="While ticked, payroll deducts nothing for any loan of this company.")
    loan_deduction_pause_reason = fields.Char(string='Pause Reason')
