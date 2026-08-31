# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Rows per PDF page (landscape A4) with readable font sizes.
ROWS_PER_PAGE = 25

# Non-taxable portion of transport allowance (Ethiopian payroll practice).
TRANSPORT_TAX_FREE = 600.0
TAXABLE_TRANSPORT_CODE = "__TAXABLE_TRANSPORT__"
TAXABLE_TRANSPORT_NAME = "Taxable Transport Allowance"


def _split_header_name(name, max_chars=14):
    """Split a long column title into short lines for a compact header.
    Prefers breaking on spaces (e.g. 'Position Allowance' → ['Position', 'Allowance']).
    """
    name = (name or "").strip()
    if not name:
        return [""]
    words = name.split()
    if len(words) == 1:
        if len(name) <= max_chars:
            return [name]
        lines = []
        while name:
            lines.append(name[:max_chars])
            name = name[max_chars:]
        return lines
    lines = []
    current = words[0]
    for w in words[1:]:
        if len(current) + 1 + len(w) <= max_chars:
            current = current + " " + w
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines


def _split_employee_name(name, max_chars=20):
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


def _is_transport_column(col):
    """Detect the Transport Allowance column by label or code."""
    label = (col.get("name") or col.get("code") or "").lower()
    return "transport" in label and "taxable" not in label


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
        if not self.batch_ids:
            if self.date_from:
                domain.append(("date_from", ">=", self.date_from))
            if self.date_to:
                domain.append(("date_to", "<=", self.date_to))
        if not self.include_non_confirmed:
            domain.append(("state", "=", "done"))
        return self.env["hr.payslip"].search(domain, order="employee_id, date_from")

    def _chunk_rows(self, rows, columns):
        """Split rows into pages of ROWS_PER_PAGE and compute per-page totals."""
        pages = []
        for i in range(0, len(rows), ROWS_PER_PAGE):
            chunk = rows[i : i + ROWS_PER_PAGE]
            page_totals = {c["code"]: 0.0 for c in columns}
            for row in chunk:
                for code, amount in row["values"].items():
                    page_totals[code] = page_totals.get(code, 0.0) + amount
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

    def _insert_taxable_transport(self, columns, rows, totals):
        """Insert 'Taxable Transport Allowance' right after Transport Allowance.

        Taxable amount = max(0, transport_allowance - 600).
        """
        transport_idx = None
        transport_code = None
        for i, col in enumerate(columns):
            if _is_transport_column(col):
                transport_idx = i
                transport_code = col["code"]
                break

        if transport_idx is None:
            # No transport column found — nothing to add
            return columns, rows, totals

        taxable_col = {
            "code": TAXABLE_TRANSPORT_CODE,
            "name": TAXABLE_TRANSPORT_NAME,
            "sequence": columns[transport_idx]["sequence"] + 0.5,
            "name_lines": _split_header_name(TAXABLE_TRANSPORT_NAME),
        }
        columns = (
            columns[: transport_idx + 1]
            + [taxable_col]
            + columns[transport_idx + 1 :]
        )

        taxable_total = 0.0
        for row in rows:
            transport_amt = row["values"].get(transport_code, 0.0) or 0.0
            taxable = max(0.0, transport_amt - TRANSPORT_TAX_FREE)
            row["values"][TAXABLE_TRANSPORT_CODE] = taxable
            taxable_total += taxable

        totals[TAXABLE_TRANSPORT_CODE] = taxable_total
        return columns, rows, totals

    def _get_report_data(self):
        """Build the pivoted report data: one column per distinct salary
        rule found on the matched payslips (ordered by rule sequence), one
        row per payslip, plus a totals row. Purely dynamic - if you add,
        rename or remove salary rules, this report adapts on its own.

        Also inserts Taxable Transport Allowance (Transport - 600) next to
        Transport Allowance, and splits rows into pages for PDF page totals.
        """
        self.ensure_one()
        payslips = self._get_payslips()
        if not payslips:
            raise UserError(_("No payslips match the selected filters."))

        lines = payslips.mapped("line_ids")
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
        for col in columns:
            col["name_lines"] = _split_header_name(col["name"])

        rows = []
        totals = {c["code"]: 0.0 for c in columns}
        for payslip in payslips:
            values = {}
            for line in payslip.line_ids:
                key = line.salary_rule_id.report_group_label or line.code or line.name
                values[key] = values.get(key, 0.0) + line.total
                totals[key] = totals.get(key, 0.0) + line.total
            emp_name = payslip.employee_id.name or ""
            rows.append(
                {
                    "employee": emp_name,
                    "employee_lines": _split_employee_name(emp_name),
                    "reference": payslip.number or payslip.name or "",
                    "date_from": payslip.date_from,
                    "date_to": payslip.date_to,
                    "values": values,
                }
            )

        columns, rows, totals = self._insert_taxable_transport(columns, rows, totals)

        pages = self._chunk_rows(rows, columns)
        # Employee ~14%; remaining width split across amount columns
        col_width_pct = (86.0 / len(columns)) if columns else 10.0

        return {
            "columns": columns,
            "rows": rows,
            "pages": pages,
            "totals": totals,
            "col_width_pct": col_width_pct,
            "wizard": self,
            "company": self.env.company,
            "batches_label": ", ".join(self.batch_ids.mapped("name")) or "-",
            "period_from": min(
                (r["date_from"] for r in rows if r["date_from"]), default=False
            ),
            "period_to": max(
                (r["date_to"] for r in rows if r["date_to"]), default=False
            ),
            "generated_on": fields.Datetime.context_timestamp(
                self, fields.Datetime.now()
            ),
            "total_pages": len(pages),
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._get_report_data()
        return self.env.ref(
            "binget_payroll_reporting.action_report_hr_payslip_summary"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        self._get_report_data()
        return {
            "type": "ir.actions.act_url",
            "url": f"/binget_payroll_reporting/xlsx/{self.id}",
            "target": "self",
        }


class ReportHrPayslipSummary(models.AbstractModel):
    _name = "report.binget_payroll_reporting.report_hr_payslip_summary"
    _description = "Payroll Summary Report Parser"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env["hr.payslip.summary.report"].browse(docids)
        return wizard._get_report_data()
