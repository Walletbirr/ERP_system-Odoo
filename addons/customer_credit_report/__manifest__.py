{
    'name': 'Customer Credit Report',
    'version': '18.0.1.2.0',
    'category': 'Sales/Sales',
    'summary': 'Track outstanding customer credit (unpaid balances) from confirmed sales',
    'description': """
Customer Credit Report
=======================
Adds a "Customer Credit" report under Sales > Reporting that lists customers
who still owe money on invoiced sales orders.

Nothing is entered manually. The report is built entirely from data Odoo
already tracks (sale orders, invoices, payments), so it always stays in
sync automatically:

- Total Confirmed Sales : sum of confirmed sale orders' totals
- Total Invoiced        : total amount invoiced to the customer (native field)
- Amount Paid           : Total Invoiced - Outstanding Credit
- Outstanding Credit    : amount still owed by the customer (native field)
- Orders                : number of sale orders

Use case: dealers/sellers who issue a single invoice (e.g. a down payment)
against a sales order and need to see, at a glance, which customers still
have a balance due.
""",
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['sale', 'account'],
    'data': [
        'views/res_partner_credit_views.xml',
    ],
    'installable': True,
    'application': False,
}
