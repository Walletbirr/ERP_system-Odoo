{
    'name': 'Sales - Search by Reference',
    'version': '18.0.1.0.0',
    'summary': 'Search quotations / sales orders by their Reference '
               '(cim_reference).',
    'description': """
Sales - Search by Reference
===========================+
Small add-on for ``custom_invoice_management_sale``:

* "Reference" field in the search box of Quotations / Sales Orders.
* "Has Reference" / "No Reference" filters and a "Reference" group-by.
* The reference is also found when searching an order by name anywhere
  (Many2one dropdowns, global search).
* New menu Sales > Orders > "Search by Reference" with a list showing the
  Reference first.
""",
    'category': 'Sales/Sales',
    'depends': ['sale', 'custom_invoice_management_sale'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
