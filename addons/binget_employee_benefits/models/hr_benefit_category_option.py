# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrBenefitCategoryOption(models.Model):
    """A selectable value for a benefit category's dropdown.

    Each category owns its own list of options (add/remove as needed).
    Two kinds:
    * Fixed Amount — the option carries a static monthly amount; HR just
      picks the option, no further amount entry.
    * Named / String (e.g. "Unlimited") — the label is free text; a
      separate Amount field is shown so Accounting can set the number that
      this label resolves to. Optional dated rate history lets that number
      change over time without rewriting past periods.
    """

    _name = "hr.benefit.category.option"
    _description = "Employee Benefit Category Dropdown Option"
    _order = "category_id, sequence, name"

    name = fields.Char(
        required=True,
        help="Label shown in the dropdown when HR assigns this benefit "
        "to an employee (e.g. 'Unlimited', 'Plan A', '500 ETB').",
    )
    category_id = fields.Many2one(
        "hr.benefit.category",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="category_id.company_id", store=True)
    currency_id = fields.Many2one(related="category_id.currency_id")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    value_type = fields.Selection(
        [
            ("fixed", "Fixed Amount"),
            ("string", "Named / String"),
        ],
        string="Value Type",
        required=True,
        default="fixed",
        help="Fixed Amount: the amount is set once on this option.\n"
        "Named / String: free-text label (e.g. Unlimited); the Amount "
        "field appears so you can set the number this label resolves to. "
        "Optional rate history below lets that number change by date.",
    )
    amount = fields.Monetary(
        string="Amount",
        help="Monthly amount this option resolves to. Always used for "
        "Fixed Amount options. For Named / String options this is the "
        "fallback / current amount when no rate history applies.",
    )
    rate_ids = fields.One2many(
        "hr.benefit.rate",
        "option_id",
        string="Rate History",
        help="Only meaningful for Named / String options. When a batch is "
        "computed, the rate effective on the batch end date is used.",
    )
    note = fields.Char()

    _sql_constraints = [
        (
            "category_name_uniq",
            "unique(category_id, name)",
            "This category already has an option with that name.",
        ),
    ]

    @api.constrains("value_type", "amount")
    def _check_amount(self):
        for option in self:
            if option.value_type == "fixed" and option.amount <= 0:
                raise ValidationError(
                    "Option '%s' is a Fixed Amount and needs an amount "
                    "greater than 0." % option.name
                )
            if option.amount < 0:
                raise ValidationError(
                    "Option '%s' cannot have a negative amount." % option.name
                )

    @api.onchange("value_type")
    def _onchange_value_type(self):
        if self.value_type == "fixed":
            # Rate history is only for named/string options
            self.rate_ids = [(5, 0, 0)]

    def amount_for_date(self, date):
        """Resolve the monetary amount this option contributes on `date`.

        Fixed options always return their static amount.
        Named/string options prefer the most recent rate whose date_from
        is on or before `date`; fall back to the option's own amount.
        """
        self.ensure_one()
        if self.value_type == "fixed":
            return self.amount
        rate = self.rate_ids.filtered(lambda r: r.date_from <= date).sorted(
            "date_from", reverse=True
        )[:1]
        if rate:
            return rate.amount
        return self.amount
