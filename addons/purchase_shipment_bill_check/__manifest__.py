{
    'name': 'Purchase Bill - Shipment Arrival Check',
    'version': '18.0.1.0.0',
    'category': 'Purchase',
    'summary': 'Warn when creating a vendor bill if no linked shipment has arrived yet',
    'description': """
Purchase Bill Shipment Arrival Check
======================================

When a user clicks "Create Bill" on a Purchase Order, this module checks
whether any linked shipment (from the Shipment Tracking module) has reached
the 'arrived' state.

- If at least one linked shipment is arrived → bill creation proceeds normally.
- If no linked shipment has arrived yet → a warning popup is shown with the
  shipment reference(s) and their current status. The user can either:
    * Cancel and wait for the shipment to arrive.
    * Proceed Anyway to create the bill regardless.
- If no shipment is linked to the PO at all → bill creation proceeds normally
  (no shipment to check against).
""",
    'author': 'Your Company',
    'depends': ['purchase', 'shipment_tracking'],
    'data': [
        'security/ir.model.access.csv',
        'views/wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
