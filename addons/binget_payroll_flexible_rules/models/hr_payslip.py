# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import fields, models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    rule_ids = fields.Many2many(
        "hr.salary.rule",
        "hr_payslip_rule_rel",
        "payslip_id",
        "rule_id",
        string="Applicable Salary Rules",
        copy=False,
        help=(
            "Rules that actually apply to this payslip. Use the "
            "'Get Salary Rules' button to load every rule of the assigned "
            "salary structure (and its parents), then remove any rule that "
            "does not apply to this employee before hitting Compute Sheet. "
            "If this list is left empty, every rule of the structure is "
            "used, same as the default OCA payroll behaviour."
        ),
    )

    def action_get_salary_rules(self):
        """Load every rule of the assigned structure (and its parent
        structures) into `rule_ids`, exactly the same set the structure
        form itself lists. The user can then remove whichever rules do not
        apply to this particular employee before computing the payslip."""
        for payslip in self:
            structure_rules = super(HrPayslip, payslip)._get_salary_rules()
            payslip.rule_ids = [(6, 0, structure_rules.ids)]
        return True

    def _get_salary_rules(self):
        """Core hook used everywhere the engine needs 'the rules for this
        payslip' (computing lines, gathering inputs, etc.). If the user has
        picked a subset via `rule_ids`, honour that subset. Otherwise fall
        back to the normal structure-driven behaviour unchanged.

        Note: this can be called on an EMPTY hr.payslip recordset - e.g. the
        "Generate Payslips" batch wizard calls get_inputs() on
        self.env["hr.payslip"] as a bare helper, before any payslip records
        exist. Mirror the original method's tolerance for that: don't
        ensure_one(), just let `self.rule_ids` be falsy on an empty
        recordset and fall through to super()."""
        if self.rule_ids:
            return self.rule_ids.sorted("sequence")
        return super()._get_salary_rules()

    def onchange_employee(self):
        res = super().onchange_employee()
        # A different employee/contract may use a different structure, so
        # any previously picked rule subset is no longer meaningful - clear
        # it and let the user click "Get Salary Rules" again.
        for payslip in self:
            payslip.rule_ids = [(5, 0, 0)]
        return res
