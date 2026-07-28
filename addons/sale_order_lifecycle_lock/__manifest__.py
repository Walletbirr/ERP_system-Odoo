{
    'name': 'Sale Order Lifecycle Lock',
    'version': '18.0.1.0.0',
    'summary': 'Prevents product/line tampering after SO confirmation across Sale, Invoice and Delivery',
    'description': """
Sale Order Lifecycle Integrity
===============================
Odoo Community (and Enterprise, by default) allows confirmed sale order
lines, draft invoice lines, and pre-Done delivery lines to be freely
added, edited, or deleted with no cross-check against the originating
document. This means a Sale Order for Product A can end up invoiced
and delivered as completely different products/quantities with no
warning and no audit trail.

This module enforces one simple rule at three points in the lifecycle:

    Once a line originates from a confirmed Sale Order, its PRODUCT
    identity is locked. Quantities and logistics can still flex
    (partial delivery, backorders, discounts) but the line cannot be
    deleted or silently swapped to a different product.

Scope:
    1. sale.order.line   - no unlink, no product_id change, after confirm
    2. account.move.line - no unlink, no product_id change, for lines
                            linked back to a sale.order.line
    3. stock.move        - no unlink, no product_id change, for moves
                            linked back to a sale.order.line; plus a
                            cross-check at Validate time against the
                            originating SO's product set
    """,
    'category': 'Sales',
    'author': 'Custom',
    'depends': ['sale_management', 'account', 'stock'],
    'data': [],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
