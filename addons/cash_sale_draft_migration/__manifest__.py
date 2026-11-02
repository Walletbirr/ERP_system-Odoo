{
    'name': 'Cash Sale Draft Migration (temporary)',
    'version': '18.0.1.2.0',
    'category': 'Accounting/Accounting',
    'summary': 'One-off: convert old draft invoices of cash sales so the '
               'approved bank replaces the receivable.',
    'description': """
Temporary one-off tool. Uninstall it once the old drafts are done.

Select the old DRAFT customer invoices (list view > Action > "Convert drafts
to cash sale") and run the wizard. For each invoice it checks that:
* it is a draft customer invoice created from exactly ONE sales order;
* that order is a cash sale (Immediate Payment / Cash, not credit);
* the order has an approved payment proof with a bank;
* the approved banks add up to the invoice total.
Invoices that pass get the cash-sale flag and the bank on the line that was
Account Receivable. Optionally they are posted straight away (one JE, paid).
Anything that fails is skipped and listed with the reason; nothing is touched.
Use "Check only" first: it changes nothing.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['cash_sale_invoice_posting'],
    'data': ['security/ir.model.access.csv', 'views/wizard_views.xml'],
    'installable': True,
    'application': False,
}
