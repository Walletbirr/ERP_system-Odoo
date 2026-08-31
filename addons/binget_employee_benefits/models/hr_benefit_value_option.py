# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrBenefitValueOption(models.Model):
    """One selectable dropdown value for a benefit category (e.g. Card
    Allowance -> 'Full', 'Half', 'Unlimited'). Owned by Accounting on the
    category, same as the accounts - HR only ever picks one of these on
    the employee's benefit line, never types a number by hand.

    Two kinds of value:
    * Number  - a plain fixed amount, entered directly below.
    * Label   - a text value like "Unlimited" that is not itself a
      number, so it needs its own dated rate history so a rate change
      next year never rewrites what a past period already posted.

    Frequency is per value: the same category can have monthly amounts
    (e.g. 200/300/400 Card) and a yearly "Unlimited".
    """

    _name = "hr.benefit.value.option"
    _description = "Employee Benefit Value Option"
    _order = "category_id, sequence, name"

    category_id = fields.Many2one(
        "hr.benefit.category", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="category_id.company_id", store=True)
    currency_id = fields.Many2one(related="category_id.currency_id")
    sequence = fields.Integer(default=10)
    name = fields.Char(
        required=True, help="Shown in the dropdown, e.g. 'Full', 'Unlimited'."
    )
    value_kind = fields.Selection(
        [("number", "Number"), ("string", "Label (needs rate history)")],
        required=True,
        default="number",
        string="Value Kind",
        help="Number: the amount below is used as-is.\n"
        "Label: this value is a name (e.g. 'Unlimited'), not a number, "
        "so its amount is resolved from the dated rate history instead.",
    )
    frequency = fields.Selection(
        [("monthly", "Monthly"), ("yearly", "Yearly")],
        required=True,
        default="monthly",
        string="Frequency",
        help="How often this value is paid out. 'Monthly' values are only "
        "pulled into a Monthly batch; 'Yearly' values are only pulled "
        "into a Yearly batch. One category can mix both (e.g. fixed "
        "card amounts monthly, Unlimited yearly).",
    )
    fixed_amount = fields.Monetary(
        string="Amount",
        help="Only used when Value Kind is 'Number'. This is the amount "
        "applied whenever an employee's benefit line is set to this value.",
    )
    rate_ids = fields.One2many(
        "hr.benefit.rate", "option_id", string="Rate History"
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "category_name_uniq",
            "unique(category_id, name)",
            "This category already has a value with this name.",
        ),
    ]

    def rate_for_date(self, date):
        """Return the hr.benefit.rate effective on `date` for this
        option, i.e. the most recent rate whose date_from is on or
        before `date`. Used to resolve a 'Label' value's amount so a
        rate change this year never rewrites a past period's cost.
        """
        self.ensure_one()
        return self.rate_ids.filtered(lambda r: r.date_from <= date).sorted(
            "date_from", reverse=True
        )[:1]

    @api.constrains("value_kind", "fixed_amount")
    def _check_number_amount(self):
        for option in self:
            if option.value_kind == "number" and option.fixed_amount <= 0:
                raise ValidationError(
                    "%s: a 'Number' value needs an amount greater than 0."
                    % option.name
                )
