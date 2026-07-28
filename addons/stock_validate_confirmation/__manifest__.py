{
    'name': 'Stock Transfer Validate Confirmation',
    'version': '18.0.1.0.0',
    'summary': "Adds a 'Are you sure?' confirmation before validating any stock transfer",
    'description': """
Stock Transfer Validate Confirmation
======================================
By default, clicking "Validate" on a Receipt, Delivery, or Internal
Transfer executes immediately with no confirmation - even though it
updates stock levels and is not easily reversible.

This module inserts a simple Yes/No confirmation dialog before the
actual validation runs, for every operation type (Receipts, Deliveries,
Internal Transfers - all stock.picking under the hood).

No other behavior is changed. If the user clicks "Yes, Validate", the
normal validation proceeds exactly as before (including any backorder
wizards, immediate transfer prompts, etc. that Odoo would normally show).
    """,
    'category': 'Inventory',
    'author': 'Custom',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/stock_picking_validate_confirm_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
