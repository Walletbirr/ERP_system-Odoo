{
    'name': 'Stock Direct COGS',
    'version': '18.0.1.1.0',
    'category': 'Inventory/Accounting',
    'summary': 'Sales deliveries post COGS against Inventory directly; the '
               'customer invoice carries no stock/COGS lines.',
    'description': """
Direct COGS on delivery (no Stock Interim (Delivered))
======================================================
Standard Odoo (automatic valuation) posts, for a sale:
  delivery : Dr Stock Interim (Delivered)   Cr Inventory
  invoice  : Dr COGS                        Cr Stock Interim (Delivered)
This module changes ONLY goods that go to / come back from a customer:
  delivery : Dr COGS (the product category's expense account)   Cr Inventory
  return   : Dr Inventory   Cr COGS
  invoice  : revenue / tax / bank (or receivable) only - no stock or COGS lines
Each valuation entry gets the customer, the CSI sale reference (the order's
Reference from custom_invoice_management_sale) followed by the delivery number
(only the delivery number when there is no CSI), and a label like

"COGS - CUSTOMER - Item: CODE - Product name".

Receipts, purchases, scrap, inventory adjustments, internal moves and
dropshipping are NOT touched. Nothing changes on products or categories.
Entries posted before installation stay as they are.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['sale_stock', 'stock_account'],
    'installable': True,
    'application': False,
}
