# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
from odoo import fields, models


class HrBenefitCategory(models.Model):
    """Master data for a non-payroll employee benefit (e.g. Mobile/Airtime
    Card). HR owns creating the category itself and its dropdown of
    selectable values (option_ids) - that is the list of benefits HR can
    assign to an employee. GL accounts and journal are configured once
    for all categories under Accounting > Employee Benefits > Account
    Configuration (hr.benefit.account.config).

    Frequency lives on each value option, not on the category, so one
    category (e.g. Card Allowance) can mix monthly amounts and a yearly
    "Unlimited" plan.
    """

    _name = "hr.benefit.category"
    _description = "Employee Benefit Category (Non-Payroll)"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(help="Short reference code, e.g. MOBILE.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id")

    option_ids = fields.One2many(
        "hr.benefit.value.option", "category_id", string="Values"
    )

    note = fields.Text()

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "A benefit category with this code already exists for this company.",
        ),
    ]
