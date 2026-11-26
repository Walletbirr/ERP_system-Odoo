{
    'name': 'Purchase Bank Payments',
    'version': '1.0',
    'summary': 'Pay purchase orders straight from the bank to GIT, with one '
               'Payments button and a clear payment status on every PO.',
    'category': 'Inventory/Purchase',
    'license': 'LGPL-3',
    'depends': ['purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/purchase_bank_payment_views.xml',
        'views/purchase_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'purchase_bank_payment/static/src/css/payments.css',
        ],
    },
    'installable': True,
}
