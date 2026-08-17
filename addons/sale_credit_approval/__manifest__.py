# -*- coding: utf-8 -*-
{
    'name': 'Sales Credit Order Approval',
    'version': '18.0.1.3.0',
    'category': 'Sales',
    'summary': 'Require High-Level Manager approval before confirming any Sales Order',
    'description': """
        Adds a manager-approval workflow that applies to EVERY Sales Order,
        regardless of payment term.

        - When a Sales Order is confirmed, an approval request (activity +
          chatter notification) is sent to the High-Level Manager configured
          in Executive Dashboard > Configuration > Approval Settings.
        - The order cannot be confirmed until that manager approves it.
        - An "Approvals" tab on the Sales Order shows the full approval
          trail (Sales submission + Manager decision).
        - A notification bell in the Executive Dashboard's top navbar shows
          the current manager's pending request count.
    """,
    'author': 'BINGET HOLDING PLC',
    'depends': [
        'sale_management',
        'account',
        'mail',
        'bh_management_dashboard',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/bh_approval_config_data.xml',
        'views/sale_order_views.xml',
        'views/sale_order_approval_list_views.xml',
        'views/bh_approval_config_views.xml',
        'report/sale_order_report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_credit_approval/static/src/scss/credit_approval.scss',
            'sale_credit_approval/static/src/css/dashboard_approvals.css',
            'sale_credit_approval/static/src/xml/dashboard_approvals.xml',
            'sale_credit_approval/static/src/js/dashboard_approvals.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
