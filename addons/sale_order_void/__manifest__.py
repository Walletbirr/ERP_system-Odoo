{
    'name': 'Void Sales Order',
    'version': '18.0.1.0.5',
    'category': 'Sales',
    'summary': 'Void a complete sales order: deliveries, invoices and '
               'payments go back to where they were and every document is '
               'marked Void (cash sales and credit sales)',
    'description': """
Void Sales Order
================
A "Void Sale" button on a confirmed sales order (cash sale or credit sale).
After the accountant gives a reason and confirms, everything is done in ONE
transaction (if one step fails, nothing is changed):

* Payments reconciled only with this order's invoices: unreconciled and set
  to VOID, the same way the Void checkbox of Multi Line Payments works (zero
  value entry, status Void, the voucher number is kept; the original amount
  is saved on the payment).
* Payments that also paid other documents, or that carry an unused credit:
  only unreconciled from this order and kept as customer credit.
* Invoices and credit notes: reset to draft and cancelled (a reversal entry
  is used instead when the journal locks posted entries with a hash).
  Cash sale invoices (bank line instead of receivable) are handled the same
  way, so the bank entry disappears.
* Deliveries: when the Delivery Set to Draft module is installed, a done
  delivery is reversed IN PLACE (stock and valuation restored on the same
  delivery, then cancelled), so everything stays on the sale's own delivery.
  Without it, a done delivery is returned with a validated return picking.
  Open deliveries are cancelled.
* Payment proofs of the order are marked void when the proof model has a
  matching status.
* The sales order is cancelled and marked VOID.

Every voided document shows a VOID ribbon, the reason, the date and who
voided it. A voided document cannot be set back to draft.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['sale', 'account', 'multi_line_payment',
                'accounting_so_invoice_bridge'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/void_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/voided_sales_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
    ],
    'installable': True,
    'application': False,
}
