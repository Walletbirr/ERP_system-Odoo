# -*- coding: utf-8 -*-
{
    'name': 'Sales Approval',
    'version': '18.0.1.6.0',
    'category': 'Sales',
    'summary': 'High-Level Manager approval of Sales Orders (after Accounting approves the payment)',
    'description': """
        Adds a High-Level Manager approval step to Sales Orders.

        - An approval request (activity + chatter notification) is sent to
          the High-Level Manager configured in Executive Dashboard >
          Configuration > Approval Settings.
        - With accounting_so_invoice_bridge installed the request is sent
          automatically AFTER Accounting approves the payment proof; the
          salesperson can create the invoice only once the manager approves.
        - Credit sales (customer_credit_report, via the bridge) are sent by
          the salesperson BEFORE confirmation; approving confirms the order
          (if confirmation fails, the approval is kept and the salesperson
          confirms).
        - An "Approvals" tab on the Sales Order shows the full approval
          trail (Sales / Accounting submission + Manager decision).
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
