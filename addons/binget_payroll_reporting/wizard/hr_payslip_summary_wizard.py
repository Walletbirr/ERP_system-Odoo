# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrPayslipSummaryReport(models.TransientModel):
    _name = "hr.payslip.summary.report"
    _description = "Payroll Summary Report Wizard"

    batch_ids = fields.Many2many(
        "hr.payslip.run",
        string="Payslip Batches",
        help="Leave empty to filter by employee(s) only.",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        string="Employees",
        help="Leave empty to include every employee found in the selected "
        "batch(es).",
    )
    date_from = fields.Date(string="Date From")
    date_to = fields.Date(string="Date To")
    include_non_confirmed = fields.Boolean(
        string="Include non-confirmed payslips",
        default=False,
        help="By default only payslips in the 'Done' state are included, "
        "since those are the ones that reflect final, posted figures.",
    )

    @api.onchange("batch_ids")
    def _onchange_batch_ids(self):
        dates = self.batch_ids.mapped("date_start") + self.batch_ids.mapped(
            "date_end"
        )
        dates = [d for d in dates if d]
        if dates:
            self.date_from = min(dates)
            self.date_to = max(dates)

    def _get_payslips(self):
        self.ensure_one()
        domain = []
        if self.batch_ids:
            domain.append(("payslip_run_id", "in", self.batch_ids.ids))
        if self.employee_ids:
            domain.append(("employee_id", "in", self.employee_ids.ids))
        if not domain:
            raise UserError(
                _("Select at least one batch or one employee before printing.")
            )
        # The date range is only used as a real filter when no batch is
        # selected (pure employee-based lookup). Once a batch is picked, the
        # batch membership alone determines what's included - this avoids
        # any edge case where combining non-contiguous batches (e.g. one in
        # March, one in September) and then manually narrowing the date
        # fields could accidentally exclude one of the batches.
        if not self.batch_ids:
            if self.date_from:
                domain.append(("date_from", ">=", self.date_from))
            if self.date_to:
                domain.append(("date_to", "<=", self.date_to))
        if not self.include_non_confirmed:
            domain.append(("state", "=", "done"))
        return self.env["hr.payslip"].search(domain, order="employee_id, date_from")

    def _get_report_data(self):
        """Build the pivoted report data: one column per distinct salary
        rule found on the matched payslips (ordered by rule sequence), one
        row per payslip, plus a totals row. Purely dynamic - if you add,
        rename or remove salary rules, this report adapts on its own."""
        self.ensure_one()
        payslips = self._get_payslips()
        if not payslips:
            raise UserError(_("No payslips match the selected filters."))

        lines = payslips.mapped("line_ids")
        # De-duplicate report columns. If a rule has a report_group_label
        # set (e.g. TRANS and TRANS2 both labelled "Transport Allowance"),
        # group and sum them under that single label - this is what makes
        # the printed report look clean/professional even though several
        # internal rules feed into it. Rules without a label keep behaving
        # exactly as before: one column per rule, keyed by its own code.
        seen = {}
        for line in lines:
            rule = line.salary_rule_id
            group_key = rule.report_group_label or line.code or line.name
            display_name = rule.report_group_label or line.name
            if group_key not in seen or line.sequence < seen[group_key]["sequence"]:
                seen[group_key] = {
                    "code": group_key,
                    "name": display_name,
                    "sequence": line.sequence,
                }
        columns = [seen[c] for c in sorted(seen, key=lambda c: seen[c]["sequence"])]

        rows = []
        totals = {c["code"]: 0.0 for c in columns}
        for payslip in payslips:
            values = {}
            for line in payslip.line_ids:
                key = line.salary_rule_id.report_group_label or line.code or line.name
                values[key] = values.get(key, 0.0) + line.total
                totals[key] = totals.get(key, 0.0) + line.total
            rows.append(
                {
                    "employee": payslip.employee_id.name,
                    "reference": payslip.number or payslip.name,
                    "date_from": payslip.date_from,
                    "date_to": payslip.date_to,
                    "values": values,
                }
            )

        return {
            "columns": columns,
            "rows": rows,
            "totals": totals,
            "wizard": self,
            "company": self.env.company,
            "batches_label": ", ".join(self.batch_ids.mapped("name")) or "-",
            "period_from": min((r["date_from"] for r in rows if r["date_from"]), default=False),
            "period_to": max((r["date_to"] for r in rows if r["date_to"]), default=False),
            "generated_on": fields.Datetime.context_timestamp(
                self, fields.Datetime.now()
            ),
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._get_report_data()  # validates filters before opening the report
        return self.env.ref(
            "binget_payroll_reporting.action_report_hr_payslip_summary"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        self._get_report_data()  # validates filters before hitting the controller
        return {
            "type": "ir.actions.act_url",
            "url": f"/binget_payroll_reporting/xlsx/{self.id}",
            "target": "self",
        }


class ReportHrPayslipSummary(models.AbstractModel):
    # Name must be "report.<report_name>" where <report_name> matches the
    # `report_name` field of the ir.actions.report record - this is how
    # Odoo's qweb-pdf rendering finds the parser and calls
    # _get_report_values(docids, data) to build the template context.
    _name = "report.binget_payroll_reporting.report_hr_payslip_summary"
    _description = "Payroll Summary Report Parser"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env["hr.payslip.summary.report"].browse(docids)
        return wizard._get_report_data()
