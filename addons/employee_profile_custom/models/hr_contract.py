# -*- coding: utf-8 -*-
from odoo import api, models


class HrContract(models.Model):
    _inherit = 'hr.contract'

    @api.onchange('job_id')
    def _onchange_job_id_profile_allowance_defaults(self):
        """Copy the Job Position's Default Allowances (Screenshot: Job
        Position > Salary & Allowances) onto this contract's allowance
        lines - the employee/contract page's job, per
        binget_payroll_compensation's own design note.

        Only fills a line that's still at its untouched 0.0 amount, so a
        value someone already typed in on this contract is never silently
        overwritten. binget_payroll_compensation's default_get already
        seeds one line per Allowance-category salary rule at 0.0; this
        just fills in the ones the Job Position has a default for.
        """
        for contract in self:
            job = contract.job_id
            if not job or not job.allowance_line_ids:
                continue
            job_defaults = {
                line.rule_id.id: line.amount for line in job.allowance_line_ids
            }
            for line in contract.allowance_line_ids:
                if not line.amount and line.rule_id.id in job_defaults:
                    line.amount = job_defaults[line.rule_id.id]

    @api.model_create_multi
    def create(self, vals_list):
        contracts = super().create(vals_list)
        # Sync from each contract explicitly (not employee.contract_id,
        # which only reflects a "running" contract and may still be empty
        # for a contract that was just created in Draft).
        for contract in contracts:
            if contract.employee_id:
                contract.employee_id._sync_allowances_from_contract(contract)
        return contracts

    def write(self, vals):
        res = super().write(vals)
        if 'allowance_line_ids' in vals or 'employee_id' in vals:
            for contract in self:
                if contract.employee_id:
                    contract.employee_id._sync_allowances_from_contract(contract)
        return res
