{
    'name': 'Customer Credit Report',
    'version': '18.0.2.5.0',
    'category': 'Sales/Sales',
    'summary': 'Credit sales: one source of truth for what customers owe, '
               'ageing, payment settlements, customer statements and the '
               'Credit Sales Report sent to the manager.',
    'description': """
Customer Credit Report
======================
Everything is read from posted accounting data (credit invoices and the
payments matched to them with the invoice's Pay button). Nothing is typed in
by hand and nothing is recomputed overnight.

* The payment term is the Sales Type: terms ticked "Credit Sale" make a
  Credit sale (labelled Sales Type on the quotation), carried to invoices.
* Credit Lines: every credit invoice with total, paid, remaining, due date,
  days overdue and ageing bucket (Not due, 1-30, 31-60, 61-90, 90+).
* Customer Credit: one row per customer (company level) with total credit,
  paid, remaining, overdue and ageing.
* Settlements: every payment matched to a credit invoice (date, amount,
  bank / journal, reference).
* Customer Statement: invoices and settlements with a running balance, on
  screen and as a PDF, for any period.
* Previous Balance: a customer's own account (contact > Accounting >
  Credit Account) carries what they owed before Odoo. Its balance before
  their first credit sale in Odoo is their Previous Balance; new credit
  sales add to the account, payments deduct from it. Nothing is posted
  for it: previous balance = account balance - unpaid credit invoices.
* Credit Payments: the salesperson records a customer payment with the
  slip and chooses what it pays (previous balance and/or credit sales,
  pre-filled oldest first; a note is required to pay a newer item before
  an older one). Accounting posts it exactly as split.
* Credit Sales Report: a frozen copy of the customer's credit position,
  created when the salesperson sends a credit sale for approval.
""",
    'author': 'BINGET HOLDING PLC',
    'license': 'LGPL-3',
    'depends': ['sale', 'account', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/credit_report_views.xml',
        'views/credit_request_views.xml',
        'views/credit_payment_views.xml',
        'views/account_payment_term_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'wizard/credit_statement_wizard_views.xml',
        'report/credit_statement_report.xml',
        'report/credit_request_report.xml',
        'views/menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
