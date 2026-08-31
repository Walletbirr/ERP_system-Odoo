# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
import calendar
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hr_benefit_batch import MONTH_SELECTION


class HrBenefitBatchGenerateWizard(models.TransientModel):
    """Quick entry point for the monthly/yearly 'All Employees' run,
    modeled on Payroll's 'Generate Payslips' wizard: pick the period
    and the employees (one, several, or all), hit Generate, and land
    straight on the resulting batch with benefits already computed and
    ready to review on the Lines tab.

    Journal is not chosen here - posting always uses Account Configuration.
    """

    _name = "hr.benefit.batch.generate.wizard"
    _description = "Generate Employee Benefits (All Employees)"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    period_type = fields.Selection(
        [("monthly", "Monthly"), ("yearly", "Yearly")],
        required=True,
        default="monthly",
        help="Monthly: generates only benefit values configured as "
        "'Monthly', for the Month/Year below. Yearly: generates only "
        "values configured as 'Yearly', for the Year below.",
    )
    month = fields.Selection(
        MONTH_SELECTION,
        default=lambda self: str(fields.Date.context_today(self).month),
        help="Only used when Period is 'Monthly'.",
    )
    # Char so the UI does not format it with thousands separators (e.g. 2,026).
    year = fields.Char(
        default=lambda self: str(fields.Date.context_today(self).year),
        required=True,
        size=4,
        help="Four-digit calendar year, e.g. 2026.",
    )
    date_from = fields.Date(compute="_compute_dates", store=True, readonly=False)
    date_to = fields.Date(compute="_compute_dates", store=True, readonly=False)
    department_id = fields.Many2one(
        "hr.department",
        domain="[('company_id', '=', company_id)]",
        help="Optional - only generate benefits for employees in this "
        "department. Leave empty to include every department.",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        string="Employees",
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        help="Select one or more employees, or leave empty to include "
        "every active employee (optionally filtered by Department).",
    )

    def _year_int(self):
        self.ensure_one()
        try:
            y = int((self.year or "").strip())
            if y < 1900 or y > 2100:
                raise ValueError
            return y
        except (TypeError, ValueError):
            raise UserError(_("Year must be a four-digit number, e.g. 2026."))

    @api.depends("period_type", "month", "year")
    def _compute_dates(self):
        for wizard in self:
            if not wizard.year:
                wizard.date_from = wizard.date_to = False
                continue
            try:
                year = int(str(wizard.year).strip())
            except (TypeError, ValueError):
                wizard.date_from = wizard.date_to = False
                continue
            if year < 1900 or year > 2100:
                wizard.date_from = wizard.date_to = False
                continue
            if wizard.period_type == "monthly" and wizard.month:
                month = int(wizard.month)
                wizard.date_from = date(year, month, 1)
                wizard.date_to = date(
                    year, month, calendar.monthrange(year, month)[1]
                )
            elif wizard.period_type == "yearly":
                wizard.date_from = date(year, 1, 1)
                wizard.date_to = date(year, 12, 31)
            else:
                wizard.date_from = wizard.date_to = False

    def _default_name(self):
        self.ensure_one()
        period = (
            str(self._year_int())
            if self.period_type == "yearly"
            else self.date_from.strftime("%B %Y")
        )
        return _("Employee Benefits - %s") % period

    def action_generate(self):
        """Create or update an All Employees batch for the chosen period,
        compute employee benefit lines, then open the batch so the Lines
        tab shows every selected employee's computed amounts.
        """
        self.ensure_one()
        if self.period_type == "monthly" and not self.month:
            raise UserError(_("Select a month."))
        if not self.date_from or not self.date_to:
            raise UserError(_("Select a valid period."))

        Batch = self.env["hr.benefit.batch"]
        vals = {
            "name": self._default_name(),
            "company_id": self.company_id.id,
            "period_type": self.period_type,
            "month": self.month,
            "year": self.year,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "department_id": self.department_id.id,
            "restrict_employee_ids": [(6, 0, self.employee_ids.ids)],
            "employee_id": False,
        }

        # If opened from an existing draft All-Employees batch, fill that
        # record instead of creating a second empty one.
        batch = False
        active_id = self.env.context.get("active_id")
        active_model = self.env.context.get("active_model")
        if active_model == "hr.benefit.batch" and active_id:
            candidate = Batch.browse(active_id)
            if (
                candidate.exists()
                and not candidate.employee_id
                and candidate.state == "draft"
            ):
                batch = candidate
                batch.write(vals)

        if not batch:
            batch = Batch.create(vals)

        batch.action_compute()

        if not batch.line_ids:
            raise UserError(
                _(
                    "No benefit lines were found for the selected period and "
                    "employees.\n\n"
                    "Check that:\n"
                    "• Employees have active benefit lines on their form "
                    "(Benefits tab),\n"
                    "• Each benefit value has Frequency set (Monthly or "
                    "Yearly) matching this run,\n"
                    "• Selected employees are active and match any "
                    "department filter."
                )
            )

        form_view = self.env.ref(
            "binget_employee_benefits.view_hr_benefit_batch_form_all"
        )
        return {
            "name": _("Employee Benefits"),
            "type": "ir.actions.act_window",
            "res_model": "hr.benefit.batch",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "res_id": batch.id,
            "target": "current",
        }
