{
    'name': 'Cash Sale Invoice Posting',
    'version': '18.0.1.2.0',
    'category': 'Accounting/Accounting',
    'summary': 'Cash sales post ONE journal entry: the approved bank(s) take '
               'the place of Accounts Receivable on the invoice.',
    'description': """
Cash sales: one journal entry, bank instead of receivable
==========================================================
Sits on top of accounting_so_invoice_bridge (which stays untouched).

* A sales order is a CASH SALE when its payment term is empty or "Immediate
  Payment" / "Cash". Credit orders (term containing "credit") and every other
  term keep the normal invoice -> payment -> reconcile flow.
* The invoice of a cash sale debits the bank account(s) approved on the
  payment proof instead of Accounts Receivable. One bank = one line; several
  banks = one line per bank. Nothing is left to reconcile.
* The invoice is paid as soon as it is posted (Register Payment disappears),
  so no second journal entry is ever created.
* Posting is blocked unless the approved bank amounts equal the invoice total.
* Credit notes on a cash invoice are blocked until Accounting decides how
  refunds must be booked (reset to draft still works).
* Odoo's rule "a receivable account must have a due date and vice versa" is
  relaxed for cash sale invoices only (account.move.line._check_payable_receivable).
* Payment Terms are required on every sales order (form + server check, and
  on confirm for old quotations).
* Changing an order between cash and credit after approval / invoicing is
  blocked. Invoices created before this module are not touched.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['accounting_so_invoice_bridge'],
    'data': ['views/account_move_views.xml'],
    'installable': True,
    'application': False,
}
