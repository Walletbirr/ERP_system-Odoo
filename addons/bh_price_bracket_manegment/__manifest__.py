{
    'name': 'Price Bracket Pricelist',
    'version': '18.0.2.2.3',
    'category': 'Sales/Sales',
    'summary': 'Apply automatic discount tiers based on product Sales Price ranges',
    'description': """
Price Bracket Pricelist
========================
Adds a new Pricelist Item "Price Type" called *Price Bracket*.

When a pricelist item uses this Price Type, the discount is no longer a
fixed percentage — instead the system looks up the product's own Sales
Price (list_price) against a configurable bracket table
(Settings > Sales > Price Brackets) and applies the matching discount
percentage automatically.

Example bracket table:
    100.00   -  1000.00  ->  0%
    1001.00  -  5000.00  ->  5%
    5001.00  - 10000.00  -> 10%
    10001.00 and above   -> 15%

Only pricelists that explicitly contain a "Price Bracket" pricelist item
are affected. All other pricelists and existing category/product
structures remain untouched.

v2.0.0 adds an optional "Enter Tax-Included Price" toggle on Fixed
Price pricelist items. When checked, you enter the final tax-included
amount negotiated with the customer and the tax-excluded Fixed Price
is calculated automatically (using the product's own taxes). Leaving
it unchecked preserves the original manual Fixed Price behavior
exactly as before.

v2.1.0 fixes tax-rate detection for rules that "Apply To" ALL
products (no single product to read a tax from) by making the Tax
Rate an explicit, editable field instead of a silent lookup. Also
fixes the helper fields' layout, which previously rendered inline
inside the native Fixed Price row and overlapped.

v2.2.0 replaces the manually-typed Tax Rate (%) with a proper Tax
(account.tax) dropdown. It auto-fills from the product's own sales
tax when a specific product is selected, or from the company's
Default Sales Tax (Accounting/Invoicing Settings) when the rule
applies to ALL products - no manual typing required, still
overridable. NOTE: this replaces the old target_tax_percent field;
rules configured under v2.1 need their Tax re-selected once from the
new dropdown.

v2.2.1 adds a pre-migrate script that removes this module's own
stale view records before upgrade data loads, preventing a
"Field does not exist" ParseError when a view-referenced field is
renamed/removed across versions (as happened going from 2.1 -> 2.2).
No functional change beyond the smoother upgrade.

v2.2.3 hides the "Tax" dropdown from the Tax-Included Price Helper
form - staff no longer see or pick an account.tax record there.
Nothing else changes: the field still exists on the model, is still
auto-filled in the background (from the product's own sales tax, or
the company's Default Sales Tax when the rule applies to ALL
products), and is still what the tax-excluded Fixed Price is
calculated from on save.
""",
    'author': 'Custom Development for Binget Holding PLC',
    'depends': ['sale', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/price_bracket_rule_views.xml',
        'views/pricelist_item_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
