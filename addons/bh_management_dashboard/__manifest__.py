# -*- coding: utf-8 -*-
{
    'name': 'BH Management Dashboard',
    'version': '18.0.1.1.0',
    'category': 'Reporting',
    'summary': 'Higher Management Reporting Dashboard for BINGET HOLDING PLC',
    'description': """
        Executive Dashboard for top-level management reporting.
        Covers Sales, Inventory, Finance, Purchase, Manufacturing, and HR KPIs.
        Restricted to CEO/GM level users.
    """,
    'author': 'BINGET HOLDING PLC',
    'depends': [
        'base',
        'sale_management',
        'stock',
        'account',
        'purchase',
        'mrp',
        'hr',
        'web',
    ],
    'data': [
        'security/bh_dashboard_security.xml',
        'security/ir.model.access.csv',
        'views/bh_dashboard_views.xml',
        'views/bh_dashboard_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'bh_management_dashboard/static/src/css/dashboard.css',
            'bh_management_dashboard/static/src/xml/dashboard.xml',
            'bh_management_dashboard/static/src/js/dashboard.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
