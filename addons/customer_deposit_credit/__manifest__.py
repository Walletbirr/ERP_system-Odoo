{
    'name': 'Customer Deposit Credit',
    'version': '18.0.1.0.0',
    'summary': 'Track customers who have paid more than they have been invoiced for (deposits / advance payments).',
    'description': """
Customer Deposit Credit
========================
Tracks customers whose total payments exceed their total invoiced amount
(i.e. they have a deposit / advance credit sitting with the company that
they can use on future orders).

Features:
---------
- Automatically detects customers with a positive deposit balance:
  Total Paid (inbound payments) - Total Invoiced - Total Refunded (outbound payments)
- Dedicated "Customer Deposits" list under Sales showing all such customers
- Smart button on the Contact form showing the live deposit balance
- Automatically recalculates when payments or invoices are posted
- Nightly safety-net recomputation via scheduled action
- Tracks money paid back to the customer (refunds/withdrawals from their deposit)
    """,
    'category': 'Sales/CRM',
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['base', 'account', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/customer_deposit_views.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
