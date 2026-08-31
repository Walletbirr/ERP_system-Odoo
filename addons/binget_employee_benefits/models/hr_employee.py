# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    benefit_line_ids = fields.One2many(
        "hr.employee.benefit.line", "employee_id", string="Benefits"
    )
    benefit_count = fields.Integer(
        compute="_compute_benefit_count", string="Benefits Count"
    )

    def _compute_benefit_count(self):
        for employee in self:
            employee.benefit_count = len(employee.benefit_line_ids)
