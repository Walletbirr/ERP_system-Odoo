# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    leave_encashment_expense_account_id = fields.Many2one(
        'account.account', string="Leave Encashment Expense Account",
        help="Debited when a leave encashment is posted (e.g. 'Leave Encashment Expense').")
    leave_encashment_payable_account_id = fields.Many2one(
        'account.account', string="Leave Encashment Payable Account",
        help="Credited for the net amount (after tax withheld) when a leave encashment is "
             "posted. Use the account the money actually pays out from - e.g. your Bank/Cash "
             "account, or 'Salaries Payable' if paid out separately later.")
    leave_encashment_tax_payable_account_id = fields.Many2one(
        'account.account', string="Leave Encashment Tax Payable Account",
        help="Credited for the tax withheld when a leave encashment is posted. This is a "
             "liability - tax you owe the tax authority, not yet remitted. Typically 'Income "
             "Tax Payable'.")
    leave_encashment_journal_id = fields.Many2one(
        'account.journal', string="Leave Encashment Journal",
        help="Journal used to post leave encashment entries (e.g. 'Miscellaneous Operations' "
             "or your Payroll journal).")
    leave_encashment_days_in_month = fields.Integer(
        string="Default Days per Month (for Daily Rate)", default=30,
        help="Divisor used to turn a monthly salary into a daily rate: "
             "Daily Rate = Salary / Days per Month.")
