{
    'name': 'Document Tracking',
    'version': '18.0.21.0.0',
    'category': 'Sales/Sales',
    'summary': 'Track vehicle document collection per unit, gated by cumulative payment',
    'description': """
Vehicle Document Release Tracking
===================================
Solves a real dealership workflow gap:

1. A client who has NOT fully paid for a vehicle cannot be marked as
   having collected its documents (title, registration, customs papers,
   etc.) - enforced, not just a convention.
2. As soon as an invoice becomes fully paid, the related vehicle line(s)
   automatically flip to "Ready for Collection".
3. If a client pays in full but does not come back for months to collect
   the paperwork, a dedicated report (Sales > Reporting > Vehicle
   Document Tracking) surfaces exactly that: fully paid, not collected,
   sorted by how long it has been waiting.

Which products require this tracking is controlled per Product Category
(a checkbox "Track Document Release") - tick it for Vehicles, leave it
off for spare parts or anything else that doesn't need this workflow.

Everything is driven off native Odoo data (account.move.payment_state)
- nothing needs to be manually kept in sync.
""",
    'author': 'Custom Development for Binget Holding PLC',
    'depends': ['account', 'sale', 'stock', 'binget_spare_parts', 'shipment_tracking'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/vehicle_id_document_type_data.xml',
        'views/product_category_views.xml',
        'views/vehicle_lot_registry_views.xml',
        'views/stock_core_views.xml',
        'views/stock_move_line_views.xml',
        'views/vehicle_vin_import_wizard_views.xml',
        'views/account_move_views.xml',
        'views/vehicle_document_tracking_views.xml',
        'views/vehicle_document_tracking_by_invoice_views.xml',
        'views/vehicle_id_document_type_views.xml',
        'views/vehicle_document_collection_wizard_views.xml',
        'views/vehicle_document_multi_collection_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}