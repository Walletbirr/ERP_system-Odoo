# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import api, fields, models


class HrJob(models.Model):
    _inherit = "hr.job"

    currency_id = fields.Many2one(
        related="company_id.currency_id", string="Currency", readonly=True
    )
    default_wage = fields.Monetary(
        string="Default Wage",
        currency_field="currency_id",
        help="Default monthly Basic Salary for this position. Copied onto "
        "a contract's Wage the moment this Job Position is selected on "
        "it - each individual contract can then be freely overridden "
        "without ever affecting this template value or other employees "
        "sharing the same position.",
    )
    allowance_line_ids = fields.One2many(
        "hr.job.allowance.line",
        "job_id",
        string="Default Allowances",
        help="Reference values for this position's typical allowances. "
        "These are informational only - they are not copied onto a "
        "contract automatically; allowances on a contract are entered "
        "directly on the employee's contract.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "allowance_line_ids" in fields_list:
            rules = self.env["hr.salary.rule"].search(
                [("category_id.code", "=", "ALW")]
            )
            res["allowance_line_ids"] = [
                (0, 0, {"rule_id": rule.id, "amount": 0.0}) for rule in rules
            ]
        return res
