"""1.x -> 2.0: the module now owns the Cash / Credit sale type. Classify the
existing orders and invoices once (same rule as a fresh install)."""
from odoo.addons.customer_credit_report.hooks import set_initial_sale_types


def migrate(cr, version):
    if not version:
        return
    set_initial_sale_types(cr)
