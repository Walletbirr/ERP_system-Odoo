# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
import calendar
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

MONTH_SELECTION = [
    ("1", "January"),
    ("2", "February"),
    ("3", "March"),
    ("4", "April"),
    ("5", "May"),
    ("6", "June"),
    ("7", "July"),
    ("8", "August"),
    ("9", "September"),
    ("10", "October"),
    ("11", "November"),
    ("12", "December"),
]


class HrBenefitBatch(models.Model):
    """Accounting's compute/post batch: Compute pulls a benefit line's
    configured value into draft lines (no manual retyping), Accounting
    reviews/adjusts, then Post creates the journal entry. Mirrors the
    Compute -> Review -> Post rhythm of a payslip batch, but is a fully
    separate model with no relation to payroll. With Employee left
    empty this is the monthly run for everyone; with Employee set it is
    scoped to just that one person, independent of the monthly run.

    Journal is never set on the batch - posting always uses the default
    journal from Account Configuration.
    """

    _name = "hr.benefit.batch"
    _description = "Employee Benefits Batch"
    _order = "date_from desc, id desc"

    name = fields.Char(required=True, copy=False)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        domain="[('company_id', '=', company_id)]",
        help="Leave empty to compute and post every employee's benefits "
        "together (the monthly run). Set one employee to compute and "
        "post just their own benefits on their own, independent of the "
        "monthly run - e.g. a card issued mid-month.",
    )
    period_type = fields.Selection(
        [("monthly", "Monthly"), ("yearly", "Yearly")],
        required=True,
        default="monthly",
        tracking=True,
        help="Monthly: computes only benefit values configured as "
        "'Monthly', for the Month/Year below. Yearly: computes only "
        "values configured as 'Yearly', for the Year below (e.g. "
        "run once a year). Frequency is set per value option, so a "
        "category can mix monthly and yearly values.",
    )
    month = fields.Selection(
        MONTH_SELECTION,
        default=lambda self: str(fields.Date.context_today(self).month),
        help="Only used when Period is 'Monthly'.",
    )
    # Char so the UI does not format it with thousands separators (e.g. 2,026)
    # or treat it like a currency amount.
    year = fields.Char(
        default=lambda self: str(fields.Date.context_today(self).year),
        required=True,
        size=4,
        help="Four-digit calendar year, e.g. 2026.",
    )
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    department_id = fields.Many2one(
        "hr.department",
        string="Department",
        domain="[('company_id', '=', company_id)]",
        help="Only used for an All Employees run (Employee left empty). "
        "Optional - restrict this run to one department. Leave empty "
        "to consider every department.",
    )
    restrict_employee_ids = fields.Many2many(
        "hr.employee",
        string="Limit To Employees",
        domain="[('company_id', '=', company_id)]",
        help="Only used for an All Employees run (Employee left empty). "
        "Optional - restrict this run to just these employees. Leave "
        "empty to include every active employee (optionally filtered "
        "by Department above).",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("computed", "Computed"),
            ("posted", "Posted"),
        ],
        default="draft",
        required=True,
        copy=False,
        tracking=True,
    )
    line_ids = fields.One2many("hr.benefit.batch.line", "batch_id", string="Lines")
    line_count = fields.Integer(compute="_compute_counts")
    move_count = fields.Integer(compute="_compute_counts")
    total_amount = fields.Monetary(compute="_compute_counts")

    def _year_int(self):
        """Parse the Char year field to int; raise if invalid."""
        self.ensure_one()
        try:
            y = int((self.year or "").strip())
            if y < 1900 or y > 2100:
                raise ValueError
            return y
        except (TypeError, ValueError):
            raise UserError(_("Year must be a four-digit number, e.g. 2026."))

    @api.depends("line_ids", "line_ids.amount", "line_ids.move_id")
    def _compute_counts(self):
        for batch in self:
            lines = batch.line_ids
            batch.line_count = len(lines)
            batch.total_amount = sum(lines.mapped("amount"))
            batch.move_count = len(lines.mapped("move_id"))

    @api.onchange("period_type", "month", "year")
    def _onchange_period(self):
        """Compute date_from/date_to from Period/Month/Year, so Accounting
        picks a period the same easy way as a payslip batch instead of
        typing two raw dates - Monthly gives the selected calendar
        month, Yearly gives the full selected calendar year.
        """
        if not self.year:
            return
        try:
            year = int(str(self.year).strip())
        except (TypeError, ValueError):
            return
        if year < 1900 or year > 2100:
            return
        if self.period_type == "monthly":
            if not self.month:
                return
            month = int(self.month)
            self.date_from = date(year, month, 1)
            self.date_to = date(
                year, month, calendar.monthrange(year, month)[1]
            )
        else:
            self.month = False
            self.date_from = date(year, 1, 1)
            self.date_to = date(year, 12, 31)
        self._onchange_batch_name()

    @api.onchange("date_from", "employee_id", "period_type", "month", "year")
    def _onchange_batch_name(self):
        if self.date_from and not self.name:
            period = (
                self.date_from.strftime("%Y")
                if self.period_type == "yearly"
                else self.date_from.strftime("%B %Y")
            )
            if self.employee_id:
                self.name = _("%(employee)s - %(period)s") % {
                    "employee": self.employee_id.name,
                    "period": period,
                }
            else:
                self.name = _("Employee Benefits - %s") % period

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            self.company_id = self.employee_id.company_id

    def action_compute(self):
        """Pull every active employee's active benefit lines into draft
        batch lines for this period - or, if this batch has a single
        Employee set, only that employee's lines, so one person's benefit
        can be computed and posted independently of the monthly run. A
        'Number' value is copied as-is; a 'Label' value (e.g. Unlimited)
        is resolved from that option's rate history for date_to.
        Frequency is taken from the value option (not the category), so
        only options matching this batch's period_type are included.
        Re-running Compute replaces any line that has not been posted
        yet, so adjusting an employee's benefit and re-computing is
        always safe.
        """
        BatchLine = self.env["hr.employee.benefit.line"]
        for batch in self:
            if batch.state == "posted":
                raise UserError(
                    _("%s is already posted - it cannot be recomputed.")
                    % batch.name
                )
            # Warn if another batch already covers the same employee(s) + period
            # and is already computed or posted (avoid silent double runs).
            domain_dup = [
                ("id", "!=", batch.id),
                ("company_id", "=", batch.company_id.id),
                ("period_type", "=", batch.period_type),
                ("date_from", "=", batch.date_from),
                ("date_to", "=", batch.date_to),
                ("state", "in", ("computed", "posted")),
            ]
            if batch.employee_id:
                domain_dup.append(("employee_id", "=", batch.employee_id.id))
            else:
                domain_dup.append(("employee_id", "=", False))
            other = self.search(domain_dup, limit=1)
            if other:
                raise UserError(
                    _(
                        "A %(period)s benefits run for this period "
                        "(%(date_from)s – %(date_to)s) already exists and is "
                        "%(state)s:\n\n"
                        "• %(name)s\n\n"
                        "Open that record to review or post it, or reset it "
                        "to draft before computing again. "
                        "This avoids posting the same period twice."
                    )
                    % {
                        "period": dict(batch._fields["period_type"].selection).get(
                            batch.period_type, batch.period_type
                        ),
                        "date_from": batch.date_from,
                        "date_to": batch.date_to,
                        "state": dict(other._fields["state"].selection).get(
                            other.state, other.state
                        ),
                        "name": other.name,
                    }
                )
            batch.line_ids.filtered(lambda l: not l.move_id).unlink()
            existing_categories = batch.line_ids.mapped(
                lambda l: (l.employee_id.id, l.category_id.id)
            )
            domain = [
                ("employee_id.company_id", "=", batch.company_id.id),
                ("employee_id.active", "=", True),
                ("active", "=", True),
                ("option_id.frequency", "=", batch.period_type),
            ]
            if batch.employee_id:
                domain.append(("employee_id", "=", batch.employee_id.id))
            else:
                if batch.department_id:
                    domain.append(
                        ("employee_id.department_id", "=", batch.department_id.id)
                    )
                if batch.restrict_employee_ids:
                    domain.append(
                        ("employee_id", "in", batch.restrict_employee_ids.ids)
                    )
            source_lines = BatchLine.search(domain)
            vals_list = []
            for line in source_lines:
                key = (line.employee_id.id, line.category_id.id)
                if key in existing_categories:
                    continue
                option = line.option_id
                if not option:
                    raise UserError(
                        _("%s: the '%s' benefit has no value selected.")
                        % (line.employee_id.name, line.category_id.name)
                    )
                if option.value_kind == "number":
                    amount = option.fixed_amount
                else:
                    rate = option.rate_for_date(batch.date_to)
                    if not rate:
                        raise UserError(
                            _(
                                "No rate is configured for value '%(option)s' "
                                "on category '%(category)s' effective on or "
                                "before %(date)s. Add one on the category "
                                "before computing this batch."
                            )
                            % {
                                "option": option.name,
                                "category": line.category_id.name,
                                "date": batch.date_to,
                            }
                        )
                    amount = rate.amount
                vals_list.append(
                    {
                        "batch_id": batch.id,
                        "employee_id": line.employee_id.id,
                        "category_id": line.category_id.id,
                        "benefit_line_id": line.id,
                        "amount": amount,
                        "include": True,
                    }
                )
            self.env["hr.benefit.batch.line"].create(vals_list)
            batch.state = "computed"
            if not batch.line_ids:
                raise UserError(
                    _(
                        "No benefit lines matched this run.\n\n"
                        "• Period is %(period)s — only values with Frequency "
                        "%(period)s are included.\n"
                        "• The employee(s) must have active Benefits on the "
                        "employee form (Benefit + Value).\n"
                        "• Example: Unlimited on Card Allowance is Yearly, "
                        "so it only appears in a Yearly run, not Monthly."
                    )
                    % {"period": dict(batch._fields["period_type"].selection).get(batch.period_type, batch.period_type)}
                )

    def action_post(self):
        """Post every included, not-yet-posted line as one journal
        entry per batch (one debit/credit pair per line), then mark the
        batch posted. Journal always comes from Account Configuration.
        """
        for batch in self:
            lines = batch.line_ids.filtered(lambda l: l.include and not l.move_id)
            if not lines:
                raise UserError(_("There is nothing left to post in %s.") % batch.name)
            lines._post_lines()
            if not batch.line_ids.filtered(lambda l: l.include and not l.move_id):
                batch.state = "posted"

    def action_reset_to_draft(self):
        for batch in self:
            if batch.line_ids.mapped("move_id"):
                raise UserError(
                    _(
                        "%s has posted entries - it cannot be reset to draft. "
                        "Reset only the individual unposted lines if needed."
                    )
                    % batch.name
                )
            batch.line_ids.unlink()
            batch.state = "draft"

    def action_view_moves(self):
        self.ensure_one()
        moves = self.line_ids.mapped("move_id")
        return {
            "name": _("Journal Entries"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", moves.ids)],
        }

    def action_open_generate_wizard(self):
        """Open the Generate modal from the All Employees form (after New).
        """
        self.ensure_one()
        ctx = dict(self.env.context)
        ctx.update({
            "active_id": self.id,
            "active_ids": self.ids,
            "active_model": "hr.benefit.batch",
            "default_period_type": self.period_type,
            "default_month": self.month,
            "default_year": self.year,
            "default_department_id": self.department_id.id,
        })
        return {
            "name": _("Generate Employee Benefits"),
            "type": "ir.actions.act_window",
            "res_model": "hr.benefit.batch.generate.wizard",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }
