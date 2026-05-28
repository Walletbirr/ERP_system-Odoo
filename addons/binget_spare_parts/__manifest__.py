{
    'name': 'Binget Spare Parts Compatibility',
    'version': '18.0.1.0.0',
    'summary': 'Compatible vehicle model mapping for spare parts',
    'author': 'Binget Holding',
    'category': 'Inventory',
    'license': 'LGPL-3',
    'depends': [
        'product',
        'stock',
        'mrp',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/mrp_bom_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}