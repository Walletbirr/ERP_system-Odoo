# -*- coding: utf-8 -*-
{
    'name': 'Account Code Allow Dash',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Allow dashes (-) in Chart of Accounts codes, e.g. 1000-07',
    'description': """
Account Code Allow Dash
========================
By default, Odoo restricts the Chart of Accounts "Code" field to only
letters, digits, and dots (regex: ^[A-Za-z0-9.]+$).

This module overrides that core validation so account codes can also
contain dashes, allowing formats like:

    1000-07
    2000-A-01

No other behavior of the account.account model is changed.
""",
    'author': 'Binget Holding',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
