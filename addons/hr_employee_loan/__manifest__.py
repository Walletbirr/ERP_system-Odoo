# -*- coding: utf-8 -*-
{
    'name': 'Employee Loan Management',
    'version': '18.0.1.1.0',
    'category': 'Human Resources',
    'summary': 'Employee loans with fixed monthly installments, hold/skip control and a Loan tab on the employee profile',
    'description': """
Employee Loan Management
========================
Standalone loan module for Odoo 18 Community.

* Loans can only be given to employees with a running contract.
* Fixed monthly installment; a repayment schedule is generated on confirmation.
* Control deductions: pause one loan, skip a single month's installment
  (it moves to the end of the schedule) or pause every deduction company-wide.
* Accounting: disbursement journal entry (Dr Loan Receivable / Cr Bank or Cash).
* Loan tab on the employee profile (employee_profile_custom) showing
  borrowed / paid / remaining and status.
* Small API for the payroll side:
    employee.get_loan_deduction_amount(date_from, date_to)
    employee._get_loan_deduction_lines(date_from, date_to)
    lines._mark_paid(paid_date, reference) / lines._revert_paid()
    """,
    'author': 'Binget Holding',
    'depends': ['hr', 'hr_contract', 'account', 'employee_profile_custom'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/hr_loan_hold_wizard_views.xml',
        'views/hr_loan_pause_wizard_views.xml',
        'views/hr_loan_confirm_wizard_views.xml',
        'views/hr_loan_views.xml',
        'views/hr_loan_line_views.xml',
        'views/hr_loan_pause_log_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_employee_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hr_employee_loan/static/src/css/hr_loan.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
