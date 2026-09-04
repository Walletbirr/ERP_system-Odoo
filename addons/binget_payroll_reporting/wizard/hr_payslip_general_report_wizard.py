# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Rows per PDF page (portrait A4, just Employee + Settled Amount columns).
ROWS_PER_PAGE = 45

# Structural salary rule code that represents an employee's net take-home pay
# on a payslip. Standard across Odoo/OCA payroll salary structures.
NET_RULE_CODE = "NET"


def _split_employee_name(name, max_chars=26):
    """Wrap long employee names onto at most 2 lines (readable, not compressed)."""
    name = (name or "").strip()
    if not name or len(name) <= max_chars:
        return [name]
    words = name.split()
    if len(words) == 1:
        return [name[:max_chars], name[max_chars:]] if len(name) > max_chars else [name]
    lines = []
    current = words[0]
    for w in words[1:]:
        if len(current) + 1 + len(w) <= max_chars:
            current = current + " " + w
        else:
            lines.append(current)
            current = w
    lines.append(current)
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    return lines


class HrPayslipGeneralReport(models.TransientModel):
    _name = "hr.payslip.general.report"
    _description = "General Payroll Report Wizard (incl. Annual Leave Encashment)"

    date_from = fields.Date(string="Date From", required=True)
    date_to = fields.Date(string="Date To", required=True)
    employee_ids = fields.Many2many(
        "hr.employee",
        string="Employees",
        help="Leave empty to include every employee who has a payslip or a "
        "leave encashment in the selected period - whether or not their "
        "payslip belongs to a batch.",
    )
    include_non_confirmed = fields.Boolean(
        string="Include non-confirmed records",
        default=False,
        help="By default only payslips in the 'Done' state and encashments "
        "in the 'Posted' state are included, since those reflect final, "
        "posted figures. Cancelled encashments are always excluded.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        if "date_from" in fields_list and not res.get("date_from"):
            res["date_from"] = today.replace(day=1)
        if "date_to" in fields_list and not res.get("date_to"):
            next_month = today.replace(day=28) + timedelta(days=4)
            res["date_to"] = next_month - timedelta(days=next_month.day)
        return res

    def _get_payslips(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_("Please set both Date From and Date To."))
        domain = [
            ("date_from", "<=", self.date_to),
            ("date_to", ">=", self.date_from),
        ]
        if self.employee_ids:
            domain.append(("employee_id", "in", self.employee_ids.ids))
        if not self.include_non_confirmed:
            domain.append(("state", "=", "done"))
        else:
            domain.append(("state", "!=", "cancel"))
        return self.env["hr.payslip"].search(domain, order="employee_id")

    def _get_encashments(self):
        self.ensure_one()
        Encashment = self.env["leave.encashment"]
        domain = [
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if self.employee_ids:
            domain.append(("employee_id", "in", self.employee_ids.ids))
        if self.include_non_confirmed:
            domain.append(("state", "!=", "cancelled"))
        else:
            domain.append(("state", "=", "posted"))
        return Encashment.search(domain, order="employee_id")

    def _chunk_rows(self, rows):
        """Split rows into pages of ROWS_PER_PAGE and compute per-page totals."""
        pages = []
        for i in range(0, len(rows), ROWS_PER_PAGE):
            chunk = rows[i : i + ROWS_PER_PAGE]
            page_totals = {
                "payslip_net": 0.0,
                "encashment_net": 0.0,
                "grand_total": 0.0,
            }
            for row in chunk:
                page_totals["payslip_net"] += row["payslip_net"]
                page_totals["encashment_net"] += row["encashment_net"]
                page_totals["grand_total"] += row["grand_total"]
            pages.append(
                {
                    "rows": chunk,
                    "page_totals": page_totals,
                    "page_num": len(pages) + 1,
                    "is_last": False,
                }
            )
        if pages:
            pages[-1]["is_last"] = True
        return pages

    def _get_report_data(self):
        """One row per employee: their total Net Pay across every matched
        payslip in the period (batched or not) PLUS the net amount of every
        matched Leave Encashment in the same period, with a combined Grand
        Total. Purely period-driven, not tied to any single batch.
        """
        self.ensure_one()
        payslips = self._get_payslips()
        encashments = self._get_encashments()
        if not payslips and not encashments:
            raise UserError(
                _("No payslips or leave encashments match the selected filters.")
            )

        by_employee = {}

        def _bucket(employee):
            if employee.id not in by_employee:
                by_employee[employee.id] = {
                    "employee": employee.name or "",
                    "employee_lines": _split_employee_name(employee.name or ""),
                    "payslip_refs": [],
                    "payslip_net": 0.0,
                    "encashment_refs": [],
                    "encashment_net": 0.0,
                }
            return by_employee[employee.id]

        for payslip in payslips:
            net = sum(
                line.total
                for line in payslip.line_ids
                if (line.code or "").upper() == NET_RULE_CODE
            )
            bucket = _bucket(payslip.employee_id)
            bucket["payslip_net"] += net
            ref = payslip.number or payslip.name or ""
            if ref:
                bucket["payslip_refs"].append(ref)

        for encashment in encashments:
            bucket = _bucket(encashment.employee_id)
            bucket["encashment_net"] += encashment.net_amount
            if encashment.name:
                bucket["encashment_refs"].append(encashment.name)

        rows = []
        for data in by_employee.values():
            data["grand_total"] = data["payslip_net"] + data["encashment_net"]
            data["payslip_refs_label"] = ", ".join(data["payslip_refs"]) or "-"
            data["encashment_refs_label"] = ", ".join(data["encashment_refs"]) or "-"
            rows.append(data)
        rows.sort(key=lambda r: r["employee"])

        totals = {
            "payslip_net": sum(r["payslip_net"] for r in rows),
            "encashment_net": sum(r["encashment_net"] for r in rows),
            "grand_total": sum(r["grand_total"] for r in rows),
        }

        pages = self._chunk_rows(rows)

        return {
            "rows": rows,
            "pages": pages,
            "totals": totals,
            "wizard": self,
            "company": self.env.company,
            "period_from": self.date_from,
            "period_to": self.date_to,
            "generated_on": fields.Datetime.context_timestamp(
                self, fields.Datetime.now()
            ),
            "total_pages": len(pages),
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._get_report_data()
        return self.env.ref(
            "binget_payroll_reporting.action_report_hr_payslip_general"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        self._get_report_data()
        return {
            "type": "ir.actions.act_url",
            "url": f"/binget_payroll_reporting/general_xlsx/{self.id}",
            "target": "self",
        }


class ReportHrPayslipGeneral(models.AbstractModel):
    _name = "report.binget_payroll_reporting.report_hr_payslip_general"
    _description = "General Payroll Report Parser"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env["hr.payslip.general.report"].browse(docids)
        return wizard._get_report_data()
