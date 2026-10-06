# -*- coding: utf-8 -*-
{
    'name': 'Multi Line Payments',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Customer and vendor payments with several accounts / purposes, like a journal entry',
    'description': """
Adds a "Multiple Lines" mode to customer and vendor payments.
Each line has its own account, partner, label (purpose) and amount.
The payment total is the sum of the lines and the journal selected on the
payment is used for the bank / cash side of the journal entry.
""",
    'depends': ['account', 'base_accounting_kit'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_payment_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
