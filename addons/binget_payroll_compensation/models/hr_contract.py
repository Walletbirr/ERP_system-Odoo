# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import api, fields, models


class HrContract(models.Model):
    _inherit = "hr.contract"

    allowance_line_ids = fields.One2many(
        "hr.contract.allowance.line",
        "contract_id",
        string="Allowances",
        help="One line per allowance this employee actually receives. "
        "Salary rule formulas read amounts from here via "
        "contract.get_allowance_amount('RULE_CODE') - add, remove, or "
        "change lines freely per employee.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "allowance_line_ids" in fields_list and not res.get(
            "allowance_line_ids"
        ):
            rules = self.env["hr.salary.rule"].search(
                [("category_id.code", "=", "ALW")]
            )
            res["allowance_line_ids"] = [
                (0, 0, {"rule_id": rule.id, "amount": 0.0}) for rule in rules
            ]
        return res

    def get_allowance_amount(self, rule_code):
        """Called from a salary rule's Python formula, e.g.:
        result = contract.get_allowance_amount('TRANS')

        Resolution order: if this contract has its own line for that rule
        code, that value wins (an override). Otherwise, falls back to the
        assigned Job Position's default for that rule code. Otherwise 0.0.
        This is what makes "every employee on a position gets that
        position's pay automatically, but can be individually overridden"
        actually work - it's resolved here at computation time, so no
        onchange, button, or copy step is required for the common case of
        an employee who just uses their position's defaults as-is."""
        self.ensure_one()
        line = self.allowance_line_ids.filtered(
            lambda l: l.rule_id.code == rule_code
        )
        if line:
            return line.amount
        if self.job_id:
            job_line = self.job_id.allowance_line_ids.filtered(
                lambda l: l.rule_id.code == rule_code
            )
            if job_line:
                return job_line.amount
        return 0.0

    @api.onchange("job_id")
    def _onchange_job_id_binget_compensation_defaults(self):
        """Populate only the Wage from the Job Position's default the
        moment a person picks that field in the form - a plain scalar
        field, low risk of clashing with any other UI work. Allowances
        are deliberately NOT auto-copied here: see
        action_load_job_position_allowances() below, which does the same
        copy but only runs when explicitly called - e.g. from a button,
        wizard, or other UI another team builds - rather than being
        forced on every job_id change by this module."""
        for contract in self:
            job = contract.job_id
            if job and job.default_wage:
                contract.wage = job.default_wage

    def action_load_job_position_allowances(self):
        """Copies the assigned Job Position's default allowance lines
        onto this contract, replacing whatever is currently there. Not
        wired to any onchange or button by this module on purpose - call
        it from wherever a UI needs this behavior (a button, a wizard,
        client-side JS, an automation rule, etc.), so the team owning the
        employee/contract UI can decide exactly when and how this fires
        without needing to touch or duplicate this logic."""
        for contract in self:
            job = contract.job_id
            if not job:
                continue
            contract.allowance_line_ids = [(5, 0, 0)] + [
                (0, 0, {"rule_id": line.rule_id.id, "amount": line.amount})
                for line in job.allowance_line_ids
            ]

    @api.onchange("employee_id")
    def _onchange_employee_id_binget_company_defaults(self):
        self._binget_apply_company_defaults()

    def _binget_apply_company_defaults(self):
        """Fill journal_id / analytic_account_id / struct_id from the
        employee's department and the company-wide Payroll configuration -
        but only when not already set, so this never overwrites a
        deliberate manual override."""
        for contract in self:
            company = contract.company_id or self.env.company
            department = contract.employee_id.department_id
            if not contract.analytic_account_id:
                contract.analytic_account_id = (
                    department.analytic_account_id
                    or company.payroll_analytic_account_id
                )
            if not contract.journal_id:
                contract.journal_id = company.payroll_journal_id
            if not contract.struct_id:
                contract.struct_id = company.payroll_structure_id

    @api.model_create_multi
    def create(self, vals_list):
        contracts = super().create(vals_list)
        # Mirrors the onchange above, but also covers contracts created
        # outside the form view - batch imports, the payslip employees
        # wizard, or any API call - where onchange never fires.
        contracts._binget_apply_company_defaults()
        return contracts

    def action_binget_backfill_payroll_defaults(self):
        """One-time (but safe to re-run anytime) catch-up for contracts
        that already existed before this module was installed, or whose
        Job Position / company Payroll settings were only filled in
        afterwards. The onchange/create hooks above only ever fire for
        brand new contracts or brand new field changes - an old contract
        that was never touched again never gets them. This method fixes
        that gap on demand, for any number of selected contracts at once.

        It only ever fills in a field that is currently blank/zero - it
        never overwrites wage, journal, analytic account, structure, or
        allowance lines that already have a real value on them, so
        running it on a mix of old and new, touched and untouched
        contracts is always safe."""
        for contract in self:
            contract._binget_apply_company_defaults()
            if (
                not contract.wage
                and contract.job_id
                and contract.job_id.default_wage
            ):
                contract.wage = contract.job_id.default_wage
            if (
                not contract.allowance_line_ids
                and contract.job_id
                and contract.job_id.allowance_line_ids
            ):
                contract.action_load_job_position_allowances()
