# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ---- Loan tab on the stepper profile (employee_profile_custom) ----
    # The stepper walks _PROFILE_STEP_ORDER; 'loan' goes right after
    # 'commitment'. Keep this list in sync if the base list changes.
    _PROFILE_STEP_ORDER = [
        'personal', 'guarantee', 'education', 'experience',
        'contract', 'allowance', 'commitment', 'loan', 'document', 'attendance',
    ]

    profile_step = fields.Selection(
        selection_add=[('loan', 'Loans')], ondelete={'loan': 'set default'})

    loan_ids = fields.One2many('hr.loan', 'employee_id', string='Loans')
    running_loan_ids = fields.One2many(
        'hr.loan', 'employee_id', string='Running Loans',
        domain=[('state', '=', 'running')])
    loan_count = fields.Integer(compute='_compute_loan_totals')
    active_loan_count = fields.Integer(compute='_compute_loan_totals')
    loan_total_amount = fields.Monetary(
        string='Total Borrowed', compute='_compute_loan_totals', currency_field='currency_id')
    loan_total_paid = fields.Monetary(
        string='Total Paid', compute='_compute_loan_totals', currency_field='currency_id')
    loan_total_remaining = fields.Monetary(
        string='Remaining', compute='_compute_loan_totals', currency_field='currency_id')

    @api.depends('loan_ids.state', 'loan_ids.loan_amount',
                 'loan_ids.amount_paid', 'loan_ids.amount_remaining')
    def _compute_loan_totals(self):
        for emp in self:
            running = emp.loan_ids.filtered(lambda l: l.state == 'running')
            started = running
            emp.loan_count = len(emp.loan_ids.filtered(lambda l: l.state != 'cancel'))
            emp.active_loan_count = len(running)
            emp.loan_total_amount = sum(started.mapped('loan_amount'))
            emp.loan_total_paid = sum(started.mapped('amount_paid'))
            emp.loan_total_remaining = sum(running.mapped('amount_remaining'))

    # ---- Buttons ----
    def action_open_loans(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hr_employee_loan.action_hr_loan')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action

    def action_create_loan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Loan',
            'res_model': 'hr.loan',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_employee_id': self.id},
        }

    # ---- API for the payroll side ----
    def _get_loan_deduction_lines(self, date_from, date_to):
        """Installments to deduct for the payroll period [date_from, date_to].

        At most ONE installment per running loan, and only if:
          * the company has not paused all deductions,
          * the loan's deduction is active,
          * the installment is due on/before date_to.
        """
        self.ensure_one()
        Line = self.env['hr.loan.line']
        if self.company_id.loan_deduction_paused:
            return Line
        loans = self.env['hr.loan'].sudo().search([
            ('employee_id', '=', self.id),
            ('state', '=', 'running'),
            ('deduction_active', '=', True),
        ])
        lines = Line
        for loan in loans:
            lines |= loan.line_ids.filtered(
                lambda l: l.state == 'pending' and l.due_date <= date_to
            ).sorted('sequence')[:1]
        return lines

    def get_loan_deduction_amount(self, date_from, date_to):
        self.ensure_one()
        return sum(self._get_loan_deduction_lines(date_from, date_to).mapped('amount'))
