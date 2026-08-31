# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrBenefitRate(models.Model):
    """A dated rate for a 'Label' value option (e.g. 'Unlimited').
    Keeping this as a history (Amount + Effective From) instead of a
    single editable field means that changing next year's rate never
    changes what past periods computed and posted.
    """

    _name = "hr.benefit.rate"
    _description = "Employee Benefit Value Rate"
    _order = "date_from desc"

    option_id = fields.Many2one(
        "hr.benefit.value.option", required=True, ondelete="cascade"
    )
    category_id = fields.Many2one(
        related="option_id.category_id", store=True, string="Category"
    )
    company_id = fields.Many2one(related="option_id.company_id", store=True)
    currency_id = fields.Many2one(related="option_id.currency_id")
    date_from = fields.Date(
        required=True,
        help="This rate applies to any period on or after this date, "
        "until a newer rate's date_from takes over.",
    )
    amount = fields.Monetary(required=True, string="Monthly Amount")
    note = fields.Char()

    _sql_constraints = [
        (
            "option_date_uniq",
            "unique(option_id, date_from)",
            "There is already a rate for this value effective on this date.",
        ),
    ]

    @api.constrains("amount")
    def _check_amount(self):
        for rate in self:
            if rate.amount < 0:
                raise ValidationError("A benefit rate amount cannot be negative.")
