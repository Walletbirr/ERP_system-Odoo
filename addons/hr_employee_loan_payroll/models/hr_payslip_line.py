# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    # copy=True on purpose: refund payslips copy their lines, and the refund
    # needs to know which installments to give back.
    loan_line_id = fields.Many2one(
        'hr.loan.line', string='Loan Installment', ondelete='set null', index=True)
    loan_id = fields.Many2one(related='loan_line_id.loan_id', string='Loan', store=True)

    def _get_partner_id(self, credit_account):
        # The partner is normally derived from the RULE's account type, but a
        # loan line posts to each loan's own receivable account -> always employee.
        if self.loan_line_id:
            emp = self.slip_id.employee_id
            return emp.work_contact_id.id or False
        return super()._get_partner_id(credit_account)
