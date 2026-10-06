{
    'name': 'Custom Invoice Management',
    'version': '18.0.3.9.4',
    'summary': 'Balance each invoice line to an agreed final selling price by auto-computing a Service Charge line (for Excise-taxed vehicle sales).',
    'description': """
Custom Invoice Management
==========================

Real-world flow this module supports:

1. A product carries two Customer Taxes: Excise Tax (e.g. 10%) then VAT
   (e.g. 15%), with Excise Tax set to "Affect Base of Subsequent Taxes"
   so VAT is computed on (Unit Price + Excise).
2. The salesperson negotiates a final, tax-included selling price with the
   customer (e.g. 490,000 Birr) that does not exactly match
   Unit Price + Excise + VAT.
3. On the Customer Invoice's "Invoice Lines" tab, the accountant enters
   that agreed amount directly on the product line, in its new
   "Selling Price" column, then clicks the "Balance" button just below
   the lines. There is no per-line VAT picker - all products are assumed
   to share the same VAT tax, so it is resolved once per invoice from
   whichever VAT (non-Excise) sale tax is already set on the product
   line(s).
4. For every line with a Selling Price set, the module adds/updates a
   dedicated "Service Charge" line (taxed at the invoice's VAT tax) with
   the exact pre-tax amount needed so Selling Price + that line's own
   tax-included amount matches exactly. Several lines can each have
   their own target on the same invoice. Service Charge lines are
   excluded from the editable "Invoice Lines" grid (they still fully
   count towards the totals/taxes and are visible in "Journal Items" and
   on the printed invoice).
5. The "Untaxed Amount / Excise Tax / Subtotal / Service Charge /
   Before Vat / Tax / Total" box at the bottom of the "Invoice Lines"
   tab is a custom display-only summary (product lines only, Service
   Charge broken out separately, "Before Vat" = Subtotal + Service
   Charge) - the real accounting fields (amount_total, tax_totals,
   journal items, printed invoice) are untouched.

Setup checklist after installing
---------------------------------
1. Accounting > Configuration > Taxes > your Excise tax > Advanced Options
   tab > enable "Affect Base of Subsequent Taxes".
2. On the vehicle product's Sales tab, set Customer Taxes to BOTH the
   Excise tax and the VAT tax (Excise listed/sequenced first).
3. On the invoice's "Invoice Lines" tab, fill in "Selling Price" on the
   line(s) you want to balance, then click "Balance".
4. (Optional) The "Service Charge Income Account" setting lives at
   Accounting > Configuration > Accounting > "Custom Invoice
   Management" (right next to "Tax Groups"), as well as under
   Accounting > Configuration > Settings > Custom Invoice Management.
   Set it to whichever account you want the auto-generated Service
   Charge line(s) to post to. If left empty, it falls back to the
   Service Charge product's own Income Account, then to its Product
   Category's Income Account. On install/upgrade, this is auto-filled
   with your company's "Other Income" account if one exists and nothing
   is set yet, so nothing needs to be done unless you want a different
   account.
""",
    'category': 'Accounting/Accounting',
    'depends': ['account'],
    'data': [
        'data/product_data.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_company_views.xml',
        'views/report_invoice_templates.xml',
        'views/report_layout_bubble.xml',
        'data/post_install_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_invoice_management/static/src/scss/cim_totals.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}
