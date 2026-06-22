{
    'name': 'Sale Order Free Quantity Validation',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Block sale order confirmation when requested quantity exceeds free (unreserved) stock',
    'description': """
Sale Order Free Quantity Validation
====================================

Prevents salespeople from confirming a Sale Order (or increasing quantity on
an already-confirmed order) when the requested quantity is greater than the
truly available stock (on hand minus what is already reserved for other
orders), checked against the warehouse selected on the order.

For example, if 20 units are on hand but 10 are already reserved for another
customer, only 10 can be sold from a new order in that warehouse - trying to
confirm an order for 15 or 20 will raise a validation error showing the
product name, the requested quantity, and the quantity actually available.
""",
    'author': 'John king',
    'depends': ['sale_stock'],
    'data': [],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
