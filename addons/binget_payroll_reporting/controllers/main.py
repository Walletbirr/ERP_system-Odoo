# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

import io

import xlsxwriter

from odoo import http
from odoo.http import request


class HrPayslipSummaryReportController(http.Controller):
    @http.route(
        "/binget_payroll_reporting/xlsx/<int:wizard_id>",
        type="http",
        auth="user",
    )
    def export_xlsx(self, wizard_id, **kwargs):
        wizard = request.env["hr.payslip.summary.report"].browse(wizard_id)
        wizard.check_access("read")
        data = wizard._get_report_data()
        company = data["company"]
        # No Reference column — only Employee + amount columns
        n_cols = 1 + len(data["columns"])

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Payroll Summary")

        # Print-friendly A4 landscape (optional when user prints from Excel)
        sheet.set_landscape()
        sheet.set_paper(9)  # A4
        sheet.set_margins(left=0.4, right=0.4, top=0.5, bottom=0.5)
        sheet.fit_to_pages(1, 0)
        sheet.center_horizontally()
        sheet.repeat_rows(0, 4)

        title_fmt = workbook.add_format(
            {
                "bold": True,
                "font_size": 14,
                "align": "center",
                "valign": "vcenter",
                "font_color": "#8B5E02",
            }
        )
        subtitle_fmt = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "align": "center",
                "valign": "vcenter",
                "font_color": "#8B5E02",
            }
        )
        meta_fmt = workbook.add_format(
            {"italic": True, "font_size": 9, "align": "left", "valign": "vcenter"}
        )
        header_fmt = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#8B5E02",
                "font_color": "white",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "font_size": 9,
            }
        )
        money_fmt = workbook.add_format(
            {
                "num_format": "#,##0.00",
                "border": 1,
                "font_size": 9,
                "valign": "vcenter",
                "align": "right",
            }
        )
        money_alt_fmt = workbook.add_format(
            {
                "num_format": "#,##0.00",
                "border": 1,
                "bg_color": "#F7F0E0",
                "font_size": 9,
                "valign": "vcenter",
                "align": "right",
            }
        )
        total_fmt = workbook.add_format(
            {
                "bold": True,
                "num_format": "#,##0.00",
                "border": 1,
                "bg_color": "#E0C98A",
                "font_color": "#3D2800",
                "font_size": 9,
                "valign": "vcenter",
                "align": "right",
            }
        )
        text_fmt = workbook.add_format(
            {
                "border": 1,
                "font_size": 9,
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        text_alt_fmt = workbook.add_format(
            {
                "border": 1,
                "bg_color": "#F7F0E0",
                "font_size": 9,
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        total_text_fmt = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "bg_color": "#E0C98A",
                "font_color": "#3D2800",
                "font_size": 9,
                "valign": "vcenter",
            }
        )

        row = 0
        sheet.set_row(row, 22)
        sheet.merge_range(row, 0, row, n_cols - 1, company.name, title_fmt)
        row += 1
        sheet.set_row(row, 18)
        sheet.merge_range(row, 0, row, n_cols - 1, "Payroll Summary", subtitle_fmt)
        row += 1
        meta_line = (
            f"Batches: {data['batches_label']}    "
            f"Period: {data['period_from'] or '-'} to {data['period_to'] or '-'}    "
            f"Generated: {data['generated_on'].strftime('%Y-%m-%d %H:%M')}"
        )
        sheet.set_row(row, 15)
        sheet.merge_range(row, 0, row, n_cols - 1, meta_line, meta_fmt)
        row += 1
        sheet.set_row(row, 6)
        row += 1

        header_row = row
        headers = ["Employee"] + [
            "\n".join(c.get("name_lines") or [c["name"]]) for c in data["columns"]
        ]
        sheet.set_row(header_row, 36)
        for col_idx, title in enumerate(headers):
            sheet.write(header_row, col_idx, title, header_fmt)
        row += 1

        for i, r in enumerate(data["rows"]):
            t_fmt = text_alt_fmt if i % 2 else text_fmt
            m_fmt = money_alt_fmt if i % 2 else money_fmt
            sheet.set_row(row, 20)
            sheet.write(row, 0, r["employee"], t_fmt)
            for col_idx, col in enumerate(data["columns"], start=1):
                sheet.write(row, col_idx, r["values"].get(col["code"], 0.0), m_fmt)
            row += 1

        # Single Grand Total only (no page totals in Excel)
        sheet.set_row(row, 22)
        sheet.write(row, 0, "Grand Total", total_text_fmt)
        for col_idx, col in enumerate(data["columns"], start=1):
            sheet.write(row, col_idx, data["totals"].get(col["code"], 0.0), total_fmt)

        sheet.set_column(0, 0, 28)  # Employee
        sheet.set_column(1, n_cols - 1, 13)

        sheet.freeze_panes(header_row + 1, 1)

        workbook.close()
        output.seek(0)

        return request.make_response(
            output.read(),
            headers=[
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet",
                ),
                (
                    "Content-Disposition",
                    "attachment; filename=Payroll_Summary.xlsx",
                ),
            ],
        )

    @http.route(
        "/binget_payroll_reporting/general_xlsx/<int:wizard_id>",
        type="http",
        auth="user",
    )
    def export_general_xlsx(self, wizard_id, **kwargs):
        wizard = request.env["hr.payslip.general.report"].browse(wizard_id)
        wizard.check_access("read")
        data = wizard._get_report_data()
        company = data["company"]
        n_cols = 2  # Employee, Settled Amount

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("General Payroll Report")

        sheet.set_paper(9)  # A4
        sheet.set_margins(left=0.4, right=0.4, top=0.5, bottom=0.5)
        sheet.fit_to_pages(1, 0)
        sheet.center_horizontally()
        sheet.repeat_rows(0, 4)

        title_fmt = workbook.add_format(
            {
                "bold": True,
                "font_size": 14,
                "align": "center",
                "valign": "vcenter",
                "font_color": "#8B5E02",
            }
        )
        subtitle_fmt = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "align": "center",
                "valign": "vcenter",
                "font_color": "#8B5E02",
            }
        )
        meta_fmt = workbook.add_format(
            {"italic": True, "font_size": 9, "align": "left", "valign": "vcenter"}
        )
        header_fmt = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#8B5E02",
                "font_color": "white",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "font_size": 9,
            }
        )
        money_fmt = workbook.add_format(
            {
                "num_format": "#,##0.00",
                "border": 1,
                "bold": True,
                "font_size": 9,
                "valign": "vcenter",
                "align": "right",
            }
        )
        money_alt_fmt = workbook.add_format(
            {
                "num_format": "#,##0.00",
                "border": 1,
                "bold": True,
                "bg_color": "#F7F0E0",
                "font_size": 9,
                "valign": "vcenter",
                "align": "right",
            }
        )
        total_fmt = workbook.add_format(
            {
                "bold": True,
                "num_format": "#,##0.00",
                "border": 1,
                "bg_color": "#E0C98A",
                "font_color": "#3D2800",
                "font_size": 9,
                "valign": "vcenter",
                "align": "right",
            }
        )
        text_fmt = workbook.add_format(
            {
                "border": 1,
                "font_size": 9,
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        text_alt_fmt = workbook.add_format(
            {
                "border": 1,
                "bg_color": "#F7F0E0",
                "font_size": 9,
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        total_text_fmt = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "bg_color": "#E0C98A",
                "font_color": "#3D2800",
                "font_size": 9,
                "valign": "vcenter",
            }
        )

        row = 0
        sheet.set_row(row, 22)
        sheet.merge_range(row, 0, row, n_cols - 1, company.name, title_fmt)
        row += 1
        sheet.set_row(row, 18)
        sheet.merge_range(
            row, 0, row, n_cols - 1,
            "General Payroll Report",
            subtitle_fmt,
        )
        row += 1
        meta_line = (
            f"Period: {data['period_from'] or '-'} to {data['period_to'] or '-'}    "
            f"Generated: {data['generated_on'].strftime('%Y-%m-%d %H:%M')}"
        )
        sheet.set_row(row, 15)
        sheet.merge_range(row, 0, row, n_cols - 1, meta_line, meta_fmt)
        row += 1
        sheet.set_row(row, 6)
        row += 1

        header_row = row
        headers = ["Employee", "Settled Amount"]
        sheet.set_row(header_row, 24)
        for col_idx, title in enumerate(headers):
            sheet.write(header_row, col_idx, title, header_fmt)
        row += 1

        for i, r in enumerate(data["rows"]):
            t_fmt = text_alt_fmt if i % 2 else text_fmt
            m_fmt = money_alt_fmt if i % 2 else money_fmt
            sheet.set_row(row, 18)
            sheet.write(row, 0, r["employee"], t_fmt)
            sheet.write(row, 1, r["grand_total"], m_fmt)
            row += 1

        sheet.set_row(row, 22)
        sheet.write(row, 0, "Grand Total", total_text_fmt)
        sheet.write(row, 1, data["totals"]["grand_total"], total_fmt)

        sheet.set_column(0, 0, 40)  # Employee
        sheet.set_column(1, n_cols - 1, 22)

        sheet.freeze_panes(header_row + 1, 1)

        workbook.close()
        output.seek(0)

        return request.make_response(
            output.read(),
            headers=[
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet",
                ),
                (
                    "Content-Disposition",
                    "attachment; filename=General_Payroll_Report.xlsx",
                ),
            ],
        )
