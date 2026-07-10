{
    'name': 'Accounting - Create Invoice from Sales Order',
    'version': '18.0.4.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Lets only users holding a dedicated custom permission (or Settings '
               'Administrators) create customer invoices from Sales Orders. '
               'Salespeople and Sales Administrators can confirm orders but can '
               'never invoice them, regardless of their native Invoicing field.',
    'description': """
Separation of Duties: Sales vs Accounting
==========================================

What this module does
----------------------
1. Restricts the native "Create Invoice" button on the Sales Order form so
   it is only visible/usable by users holding the dedicated custom group
   "Can Create Invoice from Sales Order", or Settings Administrators.
   Salespeople and Sales Administrators can confirm Sales Orders, but can
   never create an invoice or trigger payment themselves.

2. This custom group is DELIBERATELY decoupled from Odoo's native
   Invoicing/Billing access-rights field. A Sales user's native Invoicing
   field can say anything (even "Billing", if some other requirement
   forces a value into it) - it has no effect on this button. Only
   explicit assignment of the custom group by the admin turns it on. This
   also avoids the bigger problem of the native field handing over the
   entire Accounting/Invoicing app just to unlock one button.

3. Gives Billing/Accountant users read-only access to Sales Orders (only
   CONFIRMED ones - draft/sent quotations stay invisible to them), so they
   never need Sales module access to do their job.

4. Adds a filtered list under Accounting > Customers > "Create Invoice from
   Sales Order", showing confirmed orders that still need invoicing. An
   order drops off this list the moment it becomes fully invoiced.

5. Clicking a row opens the standard Sales Order form (same one used
   everywhere else in Odoo) where the now-visible "Create Invoice" button
   creates the invoice via Odoo's own native invoicing engine - nothing
   about qty_invoiced tracking, invoice_status, or Sales reporting is
   duplicated or reimplemented.

Setup after install
--------------------
Go to Settings > Users & Companies > Users > (pick the real accountant,
e.g. Million) > Access Rights tab. Under the new category "Sales Order
Invoicing (Custom)" tick "Can Create Invoice from Sales Order". That is
now the ONLY thing that turns the button on for that user - their native
Invoicing field can be left as-is or blank, it no longer matters.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['sale', 'account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/sale_order_form_views.xml',
        'views/sale_order_invoice_list_views.xml',
    ],
    'installable': True,
    'application': False,
}
