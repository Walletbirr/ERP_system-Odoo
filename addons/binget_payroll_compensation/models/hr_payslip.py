# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import api, models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    @api.onchange("contract_id")
    def _onchange_contract_id_binget_company_defaults(self):
        self._binget_apply_payslip_fallback_defaults()

    def _binget_apply_payslip_fallback_defaults(self):
        """Belt-and-suspenders fallback for the gap that let August's
        batch run silently produce dozens of all-zero payslips: the
        contract-level default-copy (see hr_contract.py) only ever ran
        at contract creation or when the Employee field was touched, so
        any contract that pre-dated the company Settings, or was never
        re-touched, stayed permanently blank - and the payslip simply
        inherited that blank.

        This makes the payslip itself fall back to the company-wide
        default whenever its own struct_id/journal_id is empty AND the
        contract it's drawing from also has nothing set - so a payslip
        can no longer end up unconfigured just because nobody ever
        re-saved the underlying contract after Settings were set."""
        for slip in self:
            company = slip.company_id or slip.env.company
            if not slip.struct_id:
                slip.struct_id = (
                    slip.contract_id.struct_id or company.payroll_structure_id
                )
            if not slip.journal_id:
                slip.journal_id = (
                    slip.contract_id.journal_id or company.payroll_journal_id
                )

    @api.model_create_multi
    def create(self, vals_list):
        slips = super().create(vals_list)
        # Mirrors the onchange above, but also covers payslips created
        # outside the form view - the "Generate Payslips" batch wizard,
        # imports, or any API call - which is exactly how August's batch
        # produced confirmed slips with nothing computed, with no error
        # ever surfacing to a user.
        slips._binget_apply_payslip_fallback_defaults()
        return slips
