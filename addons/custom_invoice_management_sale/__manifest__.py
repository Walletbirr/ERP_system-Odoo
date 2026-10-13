{
    'name': 'Custom Invoice Management - Sales',
    'version': '18.0.1.0.2',
    'summary': 'Selling Price with automatic balancing (auto Other Income line) on Quotations / '
               'Sales Orders, identical to Custom Invoice Management on Customer Invoices.',
    'description': """
Custom Invoice Management - Sales
=================================

Sales-side twin of ``custom_invoice_management``. The accounting module is
NOT modified: this bridge module adds exactly the same behaviour to
Quotations / Sales Orders and carries it through to the invoice that is
generated from the order.

What you get on a Quotation / Sales Order
------------------------------------------
* "Selling Price" column on the Order Lines grid (final tax-included price
  agreed with the customer).
* Automatic balancing: whenever the quotation is saved (or confirmed / sent /
  printed, which save it first), every line with a Selling Price gets a
  dedicated "Other Income" line (taxed with the order's VAT tax) added or
  updated so that  line total + Other Income == Selling Price. There is no
  Balance button to click.
* The Selling Price is required on every product line to confirm the order
  (a quotation can still be saved and sent without it).
* Other Income lines are hidden from the editable grid, but still count in
  totals / taxes, and still print on the quotation and the invoice.
* Custom totals box: Untaxed Amount / Excise Tax / Subtotal / Other Income /
  Before Vat / Vat / Total Before WHT / Withholding Tax / Total. Other Income
  and Before Vat are always shown (0.00 before the order is balanced).
* Parallel Seller / Buyer block + centered header on the printed quotation.

Order -> Invoice
----------------
* The Other Income line posts to the income account configured in
  Accounting > Configuration > Custom Invoice Management (the setting is
  still called "Service Charge Income Account" there).
* Selling Price and the Other Income link are carried onto the invoice, so
  the invoice's own "Balance" button updates the existing Other Income line
  instead of creating a duplicate.
""",
    'category': 'Sales/Sales',
    'depends': ['custom_invoice_management', 'sale'],
    'data': [
        'data/product_data.xml',
        'views/sale_order_views.xml',
        'views/report_sale_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_invoice_management_sale/static/src/js/sale_order_line_hide.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'auto_install': True,
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
