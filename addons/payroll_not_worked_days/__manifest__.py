{
    "name": "Payroll - Not Worked Days on Generate",
    "version": "18.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "Add Not Worked Days and Monthly Salary columns on the Generate Payslips wizard",
    "description": """
Payroll Not Worked Days
=======================

Extends the Generate Payslips wizard so HR can enter **Not Worked Days**
per employee. The value is stored as a Payslip Input with code UNPAID_DAYS
and can be used by a salary rule to deduct the corresponding amount.

Also shows the employee's current monthly salary (contract wage) in the wizard.
    """,
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["payroll"],
    "data": [
        "security/ir.model.access.csv",
        "data/hr_salary_rule_data.xml",
        "wizard/hr_payroll_payslips_by_employees_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
