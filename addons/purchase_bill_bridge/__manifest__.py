{
    'name': 'Accounting - Create Vendor Bill from Purchase Order',
    'version': '18.0.1.0.1',
    'category': 'Accounting/Accounting',
    'summary': 'Lets only users holding a dedicated custom permission (or Settings '
               'Administrators) create Vendor Bills from Purchase Orders. '
               'Purchase Officers and Purchase Administrators can confirm orders '
               'but can never bill them, regardless of their native Invoicing field.',
    'description': """
Separation of Duties: Purchase vs Accounting
==============================================

Mirrors accounting_so_invoice_bridge, for the Purchase -> Vendor Bill side.

What this module does
----------------------
1. Restricts the native "Create Bill" button on the Purchase Order form so
   it is only visible/usable by users holding the dedicated custom group
   "Can Create Bill from Purchase Order", or Settings Administrators.
   Purchase Officers and Purchase Administrators can confirm Purchase
   Orders, but can never create a bill or trigger vendor payment themselves.

2. This custom group is DELIBERATELY decoupled from Odoo's native
   Invoicing/Billing access-rights field, for the same reasons as the sale
   bridge module - a Purchase user's native Invoicing field has zero effect
   on this button. Only explicit assignment of the custom group by the
   admin turns it on.

3. Gives Billing/Accountant users read-only access to Purchase Orders (only
   CONFIRMED ones - draft/sent RFQs stay invisible to them), so they never
   need Purchase module access to do their job.

4. Adds a filtered list under Accounting > Vendors > "Create Bill from
   Purchase Order", showing confirmed orders that still need billing. An
   order drops off this list the moment it becomes fully billed.

5. Clicking a row opens the standard Purchase Order form (same one used
   everywhere else in Odoo) where the now-visible "Create Bill" button
   creates the vendor bill via Odoo's own native method - nothing about
   qty invoiced tracking or Purchase reporting is duplicated or
   reimplemented.

Setup after install
--------------------
Go to Settings > Users & Companies > Users > (pick the real accountant) >
Access Rights tab. Under the new category "Purchase Order Billing (Custom)"
tick "Can Create Bill from Purchase Order". That is the ONLY thing that
turns the button on for that user - their native Invoicing field can be
left as-is or blank, it no longer matters.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['purchase', 'account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/purchase_order_form_views.xml',
        'views/purchase_order_bill_list_views.xml',
    ],
    'installable': True,
    'application': False,
}
