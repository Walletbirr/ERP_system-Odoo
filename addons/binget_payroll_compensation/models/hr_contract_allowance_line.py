# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import fields, models


class HrContractAllowanceLine(models.Model):
    _name = "hr.contract.allowance.line"
    _description = "Contract Allowance"

    contract_id = fields.Many2one(
        "hr.contract", string="Contract", required=True, ondelete="cascade"
    )
    rule_id = fields.Many2one(
        "hr.salary.rule",
        string="Allowance",
        required=True,
        domain="[('category_id.code', '=', 'ALW')]",
    )
    currency_id = fields.Many2one(related="contract_id.currency_id", readonly=True)
    amount = fields.Monetary(string="Amount", currency_field="currency_id")

    _sql_constraints = [
        (
            "contract_rule_uniq",
            "unique(contract_id, rule_id)",
            "This allowance is already listed for this contract.",
        )
    ]
