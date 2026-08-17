# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import fields, models


class HrSalaryRule(models.Model):
    _inherit = "hr.salary.rule"

    report_group_label = fields.Char(
        string="Report Group Label",
        help=(
            "Optional. Use this to merge several internal rules into one "
            "column on the Payroll Summary Report - e.g. 'Transport "
            "Allowance' and 'Transport Allowance 2' can both be set to "
            "'Transport Allowance' here so the printed/exported report "
            "shows a single clean 'Transport Allowance' column (their "
            "amounts get summed together), while the two rules stay "
            "fully separate for actual payslip computation. Leave empty "
            "to have the rule appear under its own name, as usual."
        ),
    )
