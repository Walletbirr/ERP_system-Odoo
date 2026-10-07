# -*- coding: utf-8 -*-
{
    'name': 'Multi Line Payments',
    'version': '18.0.1.4.0',
    'category': 'Accounting',
    'summary': 'Customer and vendor payments with several accounts / purposes, like a journal entry',
    'description': """
Adds a "Multiple Lines" mode to customer and vendor payments.
Each line has its own account, partner, description and amount.
The payment amount is the total of the lines and the journal selected on the
payment is used for the bank / cash side of the journal entry.
Line amounts can be negative to put a line on the opposite side.
Confirm opens a confirmation window listing the debits and credits that will
be posted, and nothing is posted until the user agrees.
""",
    'depends': ['account', 'base_accounting_kit'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_payment_post_preview_views.xml',
        'views/account_payment_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
