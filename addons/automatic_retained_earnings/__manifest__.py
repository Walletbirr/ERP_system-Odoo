# -*- coding: utf-8 -*-
{
    'name': 'Automatic Retained Earnings (Fiscal Year Closing)',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Automatic year-end closing of Income & Expense accounts into a Retained Earnings account',
    'description': """
Automatic Retained Earnings
============================
Built for Odoo 18 Community running alongside Cybrosys' Base Accounting Kit.

What it does
------------
* Adds one new Chart of Accounts entry: a "Retained Earnings" equity account
  (created automatically per company on install, or choose your own existing
  account in Settings).
* Every Income and Expense account is tracked automatically by the system as
  usual (no extra configuration needed for that part) — this module only adds
  the year-end **closing** step.
* A "Fiscal Year Closing" wizard/record computes the balance of every P&L
  account (Income, Other Income, Expense, Depreciation, Cost of Revenue) for
  a chosen period, generates a balanced journal entry that zeroes out every
  one of those accounts, and posts the net result (profit or loss) to the
  Retained Earnings account.
* Optional scheduled action to run this automatically a day after each
  fiscal year ends.
* Every closing is reversible with one click (creates a clean reversal
  entry instead of touching/deleting the original).
""",
    'author': 'Custom Development',
    'website': 'https://www.anthropic.com',
    'license': 'LGPL-3',
    'depends': ['account', 'base_accounting_kit'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/retained_earnings_config_views.xml',
        'views/account_fiscalyear_closing_views.xml',
        'views/menu_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
