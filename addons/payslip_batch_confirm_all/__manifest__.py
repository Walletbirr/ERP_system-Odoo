# -*- coding: utf-8 -*-
{
    'name': 'Payslip Batch Confirm All',
    'version': '18.0.1.0.0',
    'summary': 'Adds a Confirm All button to Payslip Batches to confirm every payslip in one click',
    'description': """
        Adds a "Confirm All Payslips" button on the Payslips Batch (hr.payslip.run)
        form view. Clicking it computes and confirms every payslip currently in the
        batch (skipping any already confirmed or cancelled), instead of opening and
        confirming each payslip one by one.
    """,
    'category': 'Human Resources/Payroll',
    'author': 'Custom',
    'depends': ['payroll'],
    'data': [
        'views/hr_payslip_run_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
