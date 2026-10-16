# -*- coding: utf-8 -*-
{
    'name': 'Multi Line Payments',
    'version': '18.0.1.7.9',
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
A \"Void\" checkbox records a voided physical voucher: a zero value entry is
posted and the payment status becomes Void. On a void the user may pick the\naccounts in the Payment Lines tab; they are posted at 0.
The Exclude tick on payment lines is chosen by the user (no automatic tick).
""",
    'depends': ['account', 'base_accounting_kit'],
    'data': [
        'security/ir.model.access.csv',
        'security/payment_purpose_history_rule.xml',
        'views/account_payment_post_preview_views.xml',
        'views/account_payment_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'multi_line_payment/static/src/purpose_history/*',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
