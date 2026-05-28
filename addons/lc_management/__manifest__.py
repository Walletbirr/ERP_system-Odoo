{
    'name': 'LC Management',
    'version': '1.0',
    'summary': 'Letter of Credit Management',
    'depends': ['purchase', 'stock', 'account', 'base_setup'],
    'data': [
        'security/ir.model.access.csv',
        'views/lc_views.xml',
    ],
    'installable': True,
}