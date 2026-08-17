# -*- coding: utf-8 -*-
{
    'name': 'Binget GL Simple Import',
    'version': '18.0.1.0.0',
    'summary': 'Auto-convert simple GL exports into journal entries on import, with account validation',
    'description': """
Binget GL Simple Import
========================
Lets you use the standard Odoo Journal Entries "Load Data File" import with a
raw GL export (just Account, Description, Debit, Credit columns) instead of
having to manually restructure the file first.

What it does automatically when the uploaded file looks like a raw GL export:
  - Groups all lines into a single journal entry
  - Validates every account code against the Chart of Accounts. If any
    account doesn't exist, the import is blocked with a clear list of the
    missing codes - nothing gets created.
  - Checks the entry balances (total debit = total credit) before allowing
    the import to proceed.
  - Assigns the Journal automatically (first 'Miscellaneous Operations'
    type journal found) and an auto-incrementing Reference number
    (JE-0001, JE-0002, ...).

If the uploaded file is already in the full structured format (has its own
Journal/Reference columns), it is left untouched and imports normally.
""",
    'category': 'Accounting',
    'author': 'Binget Holding',
    'depends': ['base_import', 'account'],
    'data': [
        'data/ir_sequence_data.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
