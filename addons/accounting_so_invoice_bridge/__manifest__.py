{
    'name': 'Accounting - Create Invoice from Sales Order',
    'version': '18.0.13.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Lets accountants (via a dedicated custom permission, or '
               'Settings Administrators) create customer invoices from '
               'Sales Orders. Salespeople can confirm orders but can never '
               'invoice them. Also lets Sales log a payment-proof file for '
               'Accounting to see before invoicing.',
    'description': """
Separation of Duties: Sales vs Accounting
==========================================

What this module does
----------------------
1. Restricts the native "Create Invoice" button on the Sales Order form so
   it is only visible/usable by: users holding the dedicated custom group
   "Can Create Invoice from Sales Order", or Settings Administrators.
   Deliberately does NOT look at Odoo's native Invoicing field
   (Billing/Accountant) at all - on some instances that field ends up set
   on a Sales user for unrelated reasons, and trusting it here previously
   let the button (and Payment Proof edit rights) leak to people it
   shouldn't have. The dedicated group is the single, explicit source of
   truth. Salespeople and Sales Administrators can confirm Sales Orders,
   but can never create an invoice themselves.

2. Every real accountant needs the custom group ticked directly on their
   user, or wired up via a whole custom group with no code changes:
   Settings > Users & Companies > Groups > that group > Inherited Groups
   > add "Can Create Invoice from Sales Order".

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

6. Payment Proof log (sale.order.payment.proof) - a simple record of
   payment confirmation, not an approval workflow:
     - Only ever available on a CONFIRMED Sales Order (state == 'sale'),
       enforced both by the view and by a model-level constraint.
     - Hidden entirely when the order's Payment Terms name contains the
       word "credit" (e.g. "Credit 30 Days").
     - Each line: a file, optional notes, and a status of Pending
       (salesperson still attaching/fixing it) or Submitted (salesperson
       has confirmed it's ready for Accounting to look at). There is no
       Verify/Reject step - the payment already happened by the time a
       proof exists, so there's nothing for Accounting to approve.
     - Salespeople can freely add, edit, Submit, or self-service Reopen
       a line at any time. Accounting sees a strictly read-only list -
       open/download the file, see its status - and never edits it.
   The "Sales Orders: To Invoice" worklist (point 3) shows two
   quick-glance columns - whether any proof exists at all, and whether
   one has actually been Submitted - without opening each order.

7. Header stat button on the Sales Order itself, right next to the
   other smart buttons - shows Payment Proof status (Submitted /
   Pending / Not Uploaded, colour-coded) without opening the tab, and
   clicking it pops up a read-only, downloadable list of every file on
   that order. If Accounting is about to click "Create Invoice" and
   nothing has been Submitted yet, a small warning appears right next
   to the button as a heads-up - it never blocks the click.

8. The moment a quotation is confirmed into a Sales Order, a real-time
   toast notifies Accounting (Billing/Accountant users, Settings
   Administrators, and anyone with the dedicated "Can Create Invoice
   from Sales Order" group) that it's ready for them - using Odoo's own
   bus notification mechanism, no polling delay. If binget_dashboard is
   also installed, the same "ready to invoice" orders additionally show
   up in that module's own notification bell for anyone who misses the
   live toast.

Setup after install
--------------------
Nothing works automatically based on Odoo's native Invoicing field -
that field has zero effect anywhere in this module. For every real
accountant who should see "Create Invoice", tick the dedicated group
directly: Settings > Users & Companies > Users > that user > Access
Rights tab > under "Sales Order Invoicing (Custom)" tick "Can Create
Invoice from Sales Order". To wire up an entire custom group at once
instead: Settings > Users & Companies > Groups > that group > Inherited
Groups > add "Can Create Invoice from Sales Order" - no further setup
needed for anyone already in that group.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['sale', 'account', 'bus'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/sale_order_payment_proof_popup_views.xml',
        'views/sale_order_form_views.xml',
        'views/sale_order_invoice_list_views.xml',
    ],
    'installable': True,
    'application': False,
}
