# -*- coding: utf-8 -*-
from odoo import fields, models


class LeaveEncashmentSettings(models.TransientModel):
    _name = 'leave.encashment.settings'
    _description = 'Leave Encashment Accounting Settings'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    expense_account_id = fields.Many2one(
        related='company_id.leave_encashment_expense_account_id', readonly=False,
        string="Expense Account (Debit)")
    payable_account_id = fields.Many2one(
        related='company_id.leave_encashment_payable_account_id', readonly=False,
        string="Net Payable Account (Credit)")
    tax_payable_account_id = fields.Many2one(
        related='company_id.leave_encashment_tax_payable_account_id', readonly=False,
        string="Tax Payable Account (Credit)")
    journal_id = fields.Many2one(
        related='company_id.leave_encashment_journal_id', readonly=False,
        string="Posting Journal")
    days_in_month = fields.Integer(
        related='company_id.leave_encashment_days_in_month', readonly=False,
        string="Default Days per Month")

    def action_save(self):
        return {'type': 'ir.actions.act_window_close'}
