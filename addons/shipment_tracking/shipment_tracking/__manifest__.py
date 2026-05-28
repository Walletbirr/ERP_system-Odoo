# /custom_addons/shipment_tracking/__manifest__.py
{
    'name': 'Shipment & Container Tracking',
    'version': '18.0.3.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Import shipment, container tracking and local transport management',
    'description': """
        Full shipment and container tracking module for import/export business.
        Features:
        - Shipment records with ETD/ETA and port details
        - Status pipeline: Planned → In Transit → Arrived → Cleared
        - Container tracking per shipment (number, size, seal)
        - Linked to Purchase Orders
        - Incoterms support
        - Auto-generated shipment reference
        - Search by container number
        - Chatter / activity tracking
        ---
        Local Transport (NEW):
        - Create transport trips when shipment arrives at border
        - Assign one truck + driver per container
        - Per-container delivery status (Pending / In Transit / Delivered)
        - One-click load all containers from shipment
        - Smart button on Shipment form showing trip count
    """,
    'author': 'Aman',
    'depends': ['purchase', 'stock', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/shipment_views.xml',          # defines menu_shipment_root
        'views/container_views.xml',
        'views/local_transport_views.xml',   # new: local transport menu
        'views/shipment_transport_inherit.xml',  # new: adds smart button to shipment
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
