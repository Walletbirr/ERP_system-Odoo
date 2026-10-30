{
    'name': 'Delivery Set to Draft (temporary)',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Set a done delivery back to Draft, restoring stock and reverting valuation',
    'description': """
Adds a "Set to Draft" button on DONE outgoing deliveries (stock managers only).
Instead of creating a return picking it:
  * puts the delivered quantities back in the source location (and removes them
    from the destination),
  * reverses the stock valuation (reverses the original journal entries, or, if
    the delivery had no cost / no entry, books qty x product cost using the
    accounts and journal of the product category),
  * returns the delivery to Draft so it can be edited / re-confirmed.
Meant for one-time use, uninstall afterwards.
""",
    'depends': ['stock', 'stock_account'],
    'data': ['views/stock_picking_views.xml'],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
