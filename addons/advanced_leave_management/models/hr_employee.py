# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # If the Contracts module is installed you may prefer a related field to
    # hr.contract.date_start instead - kept as a plain field here so this
    # module has no hard dependency on hr_contract.
    leave_contract_start_date = fields.Date(
        string="Contract Start Date (for Leave Accrual)",
        help="Anchor date used by the leave accrual engine. If the Contracts module is "
             "installed, sync this from the employee's active contract; otherwise set manually.")

    leave_allocation_ids = fields.One2many('leave.allocation', 'employee_id', string="Leave Balances")
    leave_allocation_count = fields.Integer(compute='_compute_leave_allocation_count')

    eligible_for_leave_encashment = fields.Boolean(
        string="Eligible for Leave Encashment",
        compute='_compute_eligible_for_leave_encashment',
        search='_search_eligible_for_leave_encashment',
        help="True if this employee has at least one Expired contract on file - i.e. has "
             "left the company. Leave Encashment is restricted to former employees only.")

    @api.depends()
    def _compute_eligible_for_leave_encashment(self):
        Contract = self.env['hr.contract'].sudo()
        for emp in self:
            emp.eligible_for_leave_encashment = bool(Contract.search_count([
                ('employee_id', '=', emp.id), ('state', '=', 'close'),
            ]))

    def _search_eligible_for_leave_encashment(self, operator, value):
        Contract = self.env['hr.contract'].sudo()
        expired_employee_ids = Contract.search([('state', '=', 'close')]).mapped('employee_id').ids
        match_true = (operator == '=' and value) or (operator == '!=' and not value)
        return [('id', 'in' if match_true else 'not in', expired_employee_ids)]

    @api.depends('leave_allocation_ids')
    def _compute_leave_allocation_count(self):
        for emp in self:
            emp.leave_allocation_count = len(emp.leave_allocation_ids)

    def action_view_leave_balances(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'advanced_leave_management.action_leave_allocation')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action

    # -------------------------------------------------------------------
    # Accrual engine
    # -------------------------------------------------------------------
    def _cron_run_leave_accrual(self):
        """Scheduled job: grants accrual-bank entitlement growth for every employee
        whose next increment date (based on leave_contract_start_date + last_accrual_date)
        has been reached. Idempotent - safe to run daily.

        Growth model: the employee's OWN yearly entitlement grows by
        `increment_per_year` each period (year 1 = base_days, year 2 = base_days +
        increment_per_year, year 3 = base_days + 2*increment_per_year, ...), and
        each year's full (growing) entitlement is credited on top of whatever is
        already banked - unused leave is never reset or replaced, only added to.
        `max_days` (if set) caps the total ever credited via accrual, so growth
        flattens out instead of compounding indefinitely.
        """
        LeaveType = self.env['leave.type']
        accrual_types = LeaveType.search([('allocation_type', '=', 'accrual_bank')])
        today = fields.Date.context_today(self)
        employees = self.search([('leave_contract_start_date', '!=', False)])

        for employee in employees:
            for leave_type in accrual_types:
                allocation = self.env['leave.allocation'].search([
                    ('employee_id', '=', employee.id),
                    ('leave_type_id', '=', leave_type.id),
                ], limit=1)
                if not allocation:
                    allocation = self.env['leave.allocation'].create({
                        'employee_id': employee.id,
                        'leave_type_id': leave_type.id,
                    })

                anchor = allocation.last_accrual_date or employee.leave_contract_start_date
                period_index = 0  # 0 = year 1 (the base grant), 1 = year 2, etc.
                if not allocation.last_accrual_date:
                    # First run ever for this allocation: grant year 1's entitlement (base_days).
                    allocation._add_ledger_line(
                        move_type='accrual',
                        amount=leave_type.base_days,
                        date=employee.leave_contract_start_date,
                        reason=_('Year 1 entitlement (base)'),
                    )
                    allocation.last_accrual_date = employee.leave_contract_start_date
                    anchor = employee.leave_contract_start_date

                # Work out which period we're on by counting completed increment
                # cycles since the contract start date, so a cron restarted after
                # downtime resumes at the right year number instead of year 1.
                freq_months = leave_type.increment_frequency_months or 12
                months_elapsed = (
                    (anchor.year - employee.leave_contract_start_date.year) * 12
                    + (anchor.month - employee.leave_contract_start_date.month)
                )
                period_index = round(months_elapsed / freq_months) if months_elapsed else 0

                next_due = anchor + relativedelta(months=freq_months)
                # Grant every increment period that has elapsed, in case the cron
                # missed runs (e.g. was inactive for a while).
                while next_due <= today:
                    period_index += 1
                    granted_total = sum(allocation.ledger_line_ids.filtered(
                        lambda l: l.move_type in ('accrual', 'opening_balance')
                    ).mapped('amount'))
                    if leave_type.max_days and granted_total >= leave_type.max_days:
                        allocation.last_accrual_date = next_due
                        next_due = next_due + relativedelta(months=freq_months)
                        continue

                    # This year's own (growing) entitlement - the full amount,
                    # not just the delta - gets credited on top of the bank.
                    year_entitlement = leave_type.base_days + leave_type.increment_per_year * period_index
                    credit = year_entitlement
                    if leave_type.max_days:
                        credit = min(credit, leave_type.max_days - granted_total)
                    if credit > 0:
                        allocation._add_ledger_line(
                            move_type='accrual',
                            amount=credit,
                            date=next_due,
                            reason=_('Year %(year)s entitlement (%(amt).1f days)',
                                     year=period_index + 1, amt=year_entitlement),
                        )
                    allocation.last_accrual_date = next_due
                    next_due = next_due + relativedelta(months=freq_months)
