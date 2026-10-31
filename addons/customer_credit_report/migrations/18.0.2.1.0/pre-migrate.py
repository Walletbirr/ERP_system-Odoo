"""2.0 -> 2.1: the payment term is the Sales Type.

A payment term ticked "Credit Sale" (new field) makes a Credit sale. Before
the module loads, create that field and tick it on the terms whose name says
"credit" (the rule used until now). Existing orders and invoices keep the
Cash / Credit they already have.
"""
from odoo.tools.sql import column_exists, create_column

from odoo.addons.customer_credit_report.hooks import flag_credit_payment_terms


def migrate(cr, version):
    if not version:
        return
    if not column_exists(cr, 'account_payment_term', 'x_is_credit'):
        create_column(cr, 'account_payment_term', 'x_is_credit', 'boolean')
        flag_credit_payment_terms(cr)
