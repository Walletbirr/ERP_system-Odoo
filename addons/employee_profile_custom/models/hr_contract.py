# -*- coding: utf-8 -*-
from odoo import api, models


class HrContract(models.Model):
    _inherit = 'hr.contract'

    @api.onchange('job_id')
    def _onchange_job_id_profile_allowance_defaults(self):
        """Copy the Job Position's Default Allowances onto this contract's
        allowance lines (only fills lines still at 0.0 so manual values
        are never overwritten)."""
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

    def _seed_allowances_from_job(self):
        """Import / API path: form onchanges do not run, so contracts created
        by import arrive with empty allowance_line_ids even when the Job
        Position has Default Allowances. Copy those defaults onto the
        contract (only when the contract currently has no positive amounts)
        so payroll and the employee Allowance tab both see them.
        """
        for contract in self:
            job = contract.job_id
            if not job or not job.allowance_line_ids:
                continue
            # Already has real amounts → leave alone (manual override)
            if contract.allowance_line_ids.filtered('amount'):
                continue
            # Replace empty / zero-only lines with job defaults
            contract.allowance_line_ids = [(5, 0, 0)] + [
                (0, 0, {
                    'rule_id': line.rule_id.id,
                    'amount': line.amount,
                })
                for line in job.allowance_line_ids
                if line.rule_id
            ]

    @api.model_create_multi
    def create(self, vals_list):
        contracts = super().create(vals_list)
        # Seed from Job defaults when import/API skipped the onchange,
        # then push those lines onto the employee Allowance tab.
        contracts._seed_allowances_from_job()
        for contract in contracts:
            if contract.employee_id:
                contract.employee_id._sync_allowances_from_contract(contract)
        return contracts

    def write(self, vals):
        res = super().write(vals)
        # job_id change (or state flipping to open) should re-seed if
        # the contract still has no positive allowance amounts.
        if 'job_id' in vals or 'state' in vals:
            self._seed_allowances_from_job()
        if any(k in vals for k in (
            'allowance_line_ids', 'employee_id', 'job_id', 'state',
        )):
            for contract in self:
                if contract.employee_id:
                    contract.employee_id._sync_allowances_from_contract(contract)
        return res
