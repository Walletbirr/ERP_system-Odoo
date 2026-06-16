{
    'name': 'LC Management',
    'version': '1.0',
    'summary': 'Letter of Credit Management',
    'depends': ['purchase', 'stock', 'account', 'base_setup'],
    'author': 'John Nigus',
    'data': [
        'security/ir.model.access.csv',
        'views/lc_views.xml',
        'wizard/lc_cancel_wizard_view.xml',
    ],
    'installable': True,
}