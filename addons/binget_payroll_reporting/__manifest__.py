# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
{
    "name": "Payroll Summary Report",
    "summary": "Print/export a payroll summary (PDF & Excel) across batches or employees, "
    "with one column per salary rule",
    "version": "18.0.1.14.0",
    "category": "Human Resources/Payroll",
    "author": "Binget Holding",
    "license": "AGPL-3",
    "depends": ["payroll", "payroll_account"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_salary_rule_views.xml",
        "wizard/hr_payslip_summary_wizard_views.xml",
        "report/hr_payslip_summary_paperformat.xml",
        "report/hr_payslip_summary_report.xml",
        "report/hr_payslip_summary_template.xml",
    ],
    "installable": True,
    "application": False,
}
