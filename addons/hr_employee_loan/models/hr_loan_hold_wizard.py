# -*- coding: utf-8 -*-
from odoo import fields, models


class HrLoanHoldWizard(models.TransientModel):
    _name = 'hr.loan.hold.wizard'
    _description = 'Pause / Resume All Loan Deductions'

    company_id = fields.Many2one(
        'res.company', required=True, readonly=True,
        default=lambda self: self.env.company)
    deduction_paused = fields.Boolean(
        string='Pause all loan deductions',
        default=lambda self: self.env.company.sudo().loan_deduction_paused)
    reason = fields.Char(
        string='Reason',
        default=lambda self: self.env.company.sudo().loan_deduction_pause_reason)

    def action_apply(self):
        self.ensure_one()
        self.env['hr.loan']._check_manager()
        company = self.company_id.sudo()
        was_paused = company.loan_deduction_paused
        Loan = self.env['hr.loan'].sudo()
        Log = self.env['hr.loan.pause.log'].sudo()
        if self.deduction_paused and not was_paused:
            for loan in Loan.search([('company_id', '=', company.id), ('state', '=', 'running')]):
                Log.create({'loan_id': loan.id, 'scope': 'all', 'reason': self.reason})
                loan.message_post(body="Deduction paused for all loans: %s" % (self.reason or '-'))
        elif was_paused and not self.deduction_paused:
            Log.search([('company_id', '=', company.id), ('scope', '=', 'all'),
                        ('date_end', '=', False)])._close()
            for loan in Loan.search([('company_id', '=', company.id), ('state', '=', 'running')]):
                loan.message_post(body="Deduction resumed for all loans.")
        self.company_id.sudo().write({
            'loan_deduction_paused': self.deduction_paused,
            'loan_deduction_pause_reason': self.reason if self.deduction_paused else False,
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}
