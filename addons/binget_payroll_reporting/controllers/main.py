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
        n_cols = 2 + len(data["columns"])

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Payroll Summary")

        title_fmt = workbook.add_format(
            {"bold": True, "font_size": 16, "align": "center", "font_color": "#8B5E02"}
        )
        subtitle_fmt = workbook.add_format(
            {"bold": True, "font_size": 11, "align": "center", "font_color": "#8B5E02"}
        )
        meta_fmt = workbook.add_format({"italic": True, "font_size": 9})
        header_fmt = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#8B5E02",
                "font_color": "white",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        )
        money_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        money_alt_fmt = workbook.add_format(
            {"num_format": "#,##0.00", "border": 1, "bg_color": "#FBF3E3"}
        )
        total_fmt = workbook.add_format(
            {
                "bold": True,
                "num_format": "#,##0.00",
                "border": 1,
                "bg_color": "#F0DDB3",
                "font_color": "#5C3D01",
            }
        )
        text_fmt = workbook.add_format({"border": 1})
        text_alt_fmt = workbook.add_format({"border": 1, "bg_color": "#FBF3E3"})
        total_text_fmt = workbook.add_format(
            {"bold": True, "border": 1, "bg_color": "#F0DDB3", "font_color": "#5C3D01"}
        )

        row = 0
        sheet.merge_range(row, 0, row, n_cols - 1, company.name, title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, n_cols - 1, "Payroll Summary", subtitle_fmt)
        row += 1
        meta_line = (
            f"Batches: {data['batches_label']}    "
            f"Period: {data['period_from'] or '-'} to {data['period_to'] or '-'}    "
            f"Generated: {data['generated_on'].strftime('%Y-%m-%d %H:%M')}"
        )
        sheet.merge_range(row, 0, row, n_cols - 1, meta_line, meta_fmt)
        row += 2

        header_row = row
        headers = ["Employee", "Reference"] + [c["name"] for c in data["columns"]]
        for col_idx, title in enumerate(headers):
            sheet.write(header_row, col_idx, title, header_fmt)
        row += 1

        for i, r in enumerate(data["rows"]):
            t_fmt = text_alt_fmt if i % 2 else text_fmt
            m_fmt = money_alt_fmt if i % 2 else money_fmt
            sheet.write(row, 0, r["employee"], t_fmt)
            sheet.write(row, 1, r["reference"], t_fmt)
            for col_idx, col in enumerate(data["columns"], start=2):
                sheet.write(row, col_idx, r["values"].get(col["code"], 0.0), m_fmt)
            row += 1

        sheet.write(row, 0, "Total", total_text_fmt)
        sheet.write(row, 1, "", total_text_fmt)
        for col_idx, col in enumerate(data["columns"], start=2):
            sheet.write(row, col_idx, data["totals"].get(col["code"], 0.0), total_fmt)

        sheet.set_column(0, 1, 22)
        sheet.set_column(2, n_cols - 1, 14)
        sheet.freeze_panes(header_row + 1, 2)

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
