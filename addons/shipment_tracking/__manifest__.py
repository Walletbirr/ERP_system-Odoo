# /custom_addons/shipment_tracking/__manifest__.py
{
    'name': 'Shipment & Container Tracking',
    'version': '18.0.8.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Import shipment, container tracking and local transport management',
    'description': """
        Full shipment and container tracking module for import/export business.
        Features:
        - Shipment records with ETD/ETA and port details
        - Status pipeline: Planned → In Transit → Arrived → Cleared
        - Intermediate Ports (transshipment hubs) with per-port status tracking
        - Container tracking per shipment (number, size, seal)
        - Linked to Purchase Orders
        - Incoterms support
        - Auto-generated shipment reference
        - Search by container number or intermediate port
        - Chatter / activity tracking
        ---
        Local Transport (NEW):
        - Create transport trips when shipment arrives at border
        - Assign one truck + driver per container
        - Per-container delivery status (Pending / In Transit / Delivered)
        - One-click load all containers from shipment
        - Smart button on Shipment form showing trip count
        ---
        Receipt Validation Gate:
        - Blocks PO receipt and inventory validation until shipment is Arrived
          AND local transport trip is Delivered
    """,
    'author': 'Aman',
    'depends': ['purchase', 'stock', 'mail', 'account', 'stock_landed_costs'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/cron.xml',
        'data/shipment_cost_stage_data.xml',
        'views/shipment_views.xml',         
        'views/container_views.xml',
        'views/local_transport_views.xml',   
        'views/shipment_transport_inherit.xml',
        'views/shipment_cost_stage_views.xml',
        'views/shipment_payment_views.xml', 
        'views/stock_landed_cost_inherit_views.xml',
        'views/shipment_landed_cost_views.xml', # May be Deleted
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
