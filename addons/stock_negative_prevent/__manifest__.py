{
    'name': 'Prevent Negative Stock',
    'version': '18.0.1.0.0',
    'summary': 'Blocks Internal Transfers and Manufacturing Orders when stock is insufficient',
    'description': """
        This module prevents negative stock in two scenarios:
        1. Internal Transfers: Blocks validation when source location has insufficient quantity.
        2. Manufacturing Orders: Blocks confirmation when component stock is insufficient.
    """,
    'author': 'Custom',
    'category': 'Inventory',
    'depends': ['stock', 'mrp'],
    'data': [
        'views/stock_picking_views.xml',
        'views/mrp_production_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
