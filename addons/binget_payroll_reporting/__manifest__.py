# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
{
    "name": "Payroll Summary Report",
    "summary": "Print/export a payroll summary (PDF & Excel) across batches or employees, "
    "with one column per salary rule, plus a General Payroll Report combining "
    "payslip Net Pay with Annual Leave Encashment per employee",
    "version": "18.0.1.16.0",
    "category": "Human Resources/Payroll",
    "author": "Binget Holding",
    "license": "AGPL-3",
    "depends": ["payroll", "payroll_account", "advanced_leave_management"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_salary_rule_views.xml",
        "wizard/hr_payslip_reports_menu.xml",
        "wizard/hr_payslip_summary_wizard_views.xml",
        "wizard/hr_payslip_general_report_wizard_views.xml",
        "report/hr_payslip_summary_paperformat.xml",
        "report/hr_payslip_summary_report.xml",
        "report/hr_payslip_summary_template.xml",
        "report/hr_payslip_general_paperformat.xml",
        "report/hr_payslip_general_report.xml",
        "report/hr_payslip_general_template.xml",
    ],
    "installable": True,
    "application": False,
}
