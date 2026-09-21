# Part of Binget Holding customizations. See LICENSE file for details.

from odoo import models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def _compute_dynamic_filtered_payslip_lines(self):
        """Override of the OCA `payroll` compute.

        Original behaviour only excludes lines where
        ``appears_on_payslip`` is False, or lines that are child rules,
        when the payslip's ``hide_invisible_lines`` / ``hide_child_lines``
        fields are manually toggled on.

        Here both filters are always applied, regardless of the value of
        those two fields (they're kept on the model for data/report
        compatibility, but the form no longer exposes either toggle, and
        their values are ignored in this computation).
        """
        for payslip in self:
            lines = payslip.line_ids
            lines = lines.filtered(lambda line: not line.parent_rule_id)
            lines = lines.filtered(lambda line: line.appears_on_payslip)
            payslip.dynamic_filtered_payslip_lines = lines
