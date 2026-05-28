# /custom_addons/mrp_product_domain/__manifest__.py
{
    'name': 'MRP Product Domain Filter',
    'version': '18.0.2.0.0',
    'category': 'Manufacturing',
    'summary': 'Restricts product selection in Manufacturing Orders and Bills of Materials by category',
    'author': 'Aman',
    'depends': ['mrp'],
    'data': [
        'views/mrp_inherit_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
