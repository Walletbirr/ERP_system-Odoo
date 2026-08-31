# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
from odoo import api, fields, models


class HrEmployeeBenefitLine(models.Model):
    """A single benefit assigned to an employee (e.g. 'Card Allowance -
    Unlimited'). Edited by HR directly on the employee form. Deliberately
    has NO relation to hr.salary.rule / hr.contract - it cannot reach
    payroll because there is no field connecting the two.

    HR never types an amount here: the value is always one of the
    category's own configured dropdown options (hr.benefit.value.option),
    so what an employee can be given is controlled centrally by
    Accounting on the category, not free-typed per employee.
    """

    _name = "hr.employee.benefit.line"
    _description = "Employee Benefit (Non-Payroll)"
    _order = "employee_id, category_id"

    employee_id = fields.Many2one(
        "hr.employee", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="employee_id.company_id", store=True)
    category_id = fields.Many2one(
        "hr.benefit.category",
        required=True,
        domain="[('company_id', '=', company_id)]",
    )
    currency_id = fields.Many2one(related="category_id.currency_id")
    active = fields.Boolean(default=True)

    option_id = fields.Many2one(
        "hr.benefit.value.option",
        string="Value",
        required=True,
        domain="[('category_id', '=', category_id)]",
        help="The value for this benefit, picked from the list the "
        "category itself defines (e.g. 'Full', 'Half', 'Unlimited'). "
        "Configure the available values on the category, not here.",
    )
    current_amount = fields.Monetary(
        compute="_compute_current_amount",
        string="Current Amount",
        help="Preview only, resolved as of today. The amount actually "
        "posted is resolved again by Accounting for the batch's own "
        "period, so this can differ for a 'Label' value whose rate "
        "changes over time.",
    )
    note = fields.Char()

    _sql_constraints = [
        (
            "employee_category_uniq",
            "unique(employee_id, category_id)",
            "This employee already has a benefit line for this category.",
        ),
    ]

    @api.depends(
        "option_id.value_kind",
        "option_id.fixed_amount",
        "option_id.rate_ids.amount",
        "option_id.rate_ids.date_from",
    )
    def _compute_current_amount(self):
        today = fields.Date.context_today(self)
        for line in self:
            option = line.option_id
            if not option:
                line.current_amount = 0
            elif option.value_kind == "number":
                line.current_amount = option.fixed_amount
            else:
                rate = option.rate_for_date(today)
                line.current_amount = rate.amount if rate else 0

    @api.onchange("category_id")
    def _onchange_category_id(self):
        if self.option_id and self.option_id.category_id != self.category_id:
            self.option_id = False
