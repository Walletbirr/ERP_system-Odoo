# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import fields, models


class HrDepartment(models.Model):
    _inherit = "hr.department"

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Payroll Analytic Account",
        help=(
            "Cost-center account used for payroll journal entries of "
            "employees in this department. When set, this takes priority "
            "over the company-wide default analytic account configured "
            "in Payroll Settings."
        ),
    )
