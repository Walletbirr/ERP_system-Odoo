# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import fields, models


class HrJobAllowanceLine(models.Model):
    _name = "hr.job.allowance.line"
    _description = "Job Position Default Allowance"

    job_id = fields.Many2one(
        "hr.job", string="Job Position", required=True, ondelete="cascade"
    )
    rule_id = fields.Many2one(
        "hr.salary.rule",
        string="Allowance",
        required=True,
        domain="[('category_id.code', '=', 'ALW')]",
        help="Only salary rules under the Allowance category show up "
        "here. To add a brand new allowance type, create a new salary "
        "rule with that category (and a one-line formula referencing "
        "contract.get_allowance_amount('YOUR_CODE')) - it then appears "
        "in this dropdown automatically, with no changes needed here.",
    )
    currency_id = fields.Many2one(related="job_id.currency_id", readonly=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id")

    _sql_constraints = [
        (
            "job_rule_uniq",
            "unique(job_id, rule_id)",
            "This allowance is already listed for this Job Position.",
        )
    ]
