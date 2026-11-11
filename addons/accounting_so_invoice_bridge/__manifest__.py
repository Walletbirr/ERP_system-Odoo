{
    'name': 'Accounting - Create Invoice from Sales Order',
    'version': '18.0.31.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Accounting approves the payment proof FIRST; only then can the '
               'salesperson create the invoice, which Accounting confirms.',
    'description': """
Sales -> Accounting workflow with Payment Proof approval
=========================================================

1. Salesperson creates the quotation and confirms it.
2. Salesperson attaches the payment proof AND the client's ID on the confirmed
   Sales Order and presses Submit (not needed for "Credit" payment terms).
3. Submitting notifies Accounting (To-Do on the order + toast) and puts the
   proof on their "Payment Proofs to Review" worklist.
4. The accountant downloads the files, then Approves or Rejects (reason
   required; the salesperson fixes and resubmits).
5. When every proof is Approved, the order is sent automatically to the
   High-Level Manager (Sales Approval module). Only when the manager
   approves is the salesperson notified, and ONLY THEN does the Create
   Invoice button appear (also enforced on the server). If the manager
   rejects, the salesperson fixes the issue and presses Send to Manager.
   Credit sales (Sales Type ticked Credit Sale) instead go to the manager BEFORE
   confirmation: the salesperson presses Send Credit Request, which sends
   a Credit Sales Report (customer's credit position, ageing, open
   invoices). Once approved the order is confirmed and skips the proof.
6. The invoice is created as DRAFT; Accounting is notified a second time,
   checks the accounting setup (accounts, taxes, amounts) and confirms it.
   Only Accounting can confirm.
   BRANCH: the quotation has a Branch (where the sale happened, reporting)
   and a Deduction Branch (warehouse the stock leaves from); products not
   available in the Deduction Branch trigger a warning and block Confirm.
8. The customer invoice PDF uses a sales-invoice design: seller/buyer cards,
   info strip, products only (no Other Income line) and the full price breakdown.
7. The salesperson can open the invoice afterwards on a read-only page
   (customer, dates, products sold, the same price breakdown as the order, proof status) without any accounting
   detail (no accounts, journal items, balance, chatter).

9. PAPER INVOICES: the paper invoice number is the order's Reference (one
   number = one order or one void, never two; required before Create
   Invoice). A spoiled paper invoice is voided by the salesperson in one
   step (Sales > Orders > Void Paper Invoices): it is final and shows as
   "Void" in Accounting's Invoices list (own journal, no accounting
   effect). The salesperson enters the Invoice Date in the Create
   invoice(s) popup.

Also: Accounting has read-only access to confirmed Sales Orders and a
"Sales Invoices to Review" worklist (Accounting > Customers).

Setup after install
-------------------
Tick the accountant group on each real accountant (Settings > Users >
Access Rights > "Sales Order Invoicing (Custom)"). It is the same group as
before ("Can Create Invoice from Sales Order"), now renamed.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['sale', 'sale_stock', 'stock', 'account', 'bus', 'mail', 'sale_credit_approval',
                'custom_invoice_management', 'custom_invoice_management_sale',
                'multi_line_payment',
                'customer_credit_report'],
    'data': [
        'data/sale_stock_request_data.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        # Before account_move_views.xml: on upgrade it replaces its own
        # invoice-form extension first (18.0.31.0.0 had other buttons).
        'views/paper_invoice_views.xml',
        'views/sale_order_payment_proof_popup_views.xml',
        'views/sale_order_form_views.xml',
        'views/sale_order_branch_views.xml',
        'views/sale_stock_request_views.xml',
        'views/sale_order_invoice_list_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_register_views.xml',
        'views/account_payment_views.xml',
        'report/report_invoice_sales.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'accounting_so_invoice_bridge/static/src/js/stock_warning_request.js',
            'accounting_so_invoice_bridge/static/src/js/proof_preview.js',
            'accounting_so_invoice_bridge/static/src/js/proof_autosave.js',
        ],
    },
    'installable': True,
    'application': False,
}
