{
    'name': 'Custom Contacts Manager',
    'version': '18.0.1.2.1',
    'category': 'Sales/CRM',
    'summary': 'Categorized, secured, and redesigned Contacts app for Binget Holding',
    'description': """
Custom Contacts Manager
========================
Splits the stock Odoo Contacts (res.partner) list into proper categories
(Internal Users, Clients, Customers, Companies, Vendors) with:

* A dedicated classification model (colored, configurable, not hardcoded)
* Automatic classification of internal users
* Record rules that actually restrict data access per group (not just UI filtering)
* Separate top-level menus per category, each a scoped view of res.partner
* Custom kanban cards with category color-coding and category-specific fields
* Conditional form view fields based on contact category
""",
    'author': 'Binget Holding',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['base', 'contacts', 'mail', 'sale', 'purchase', 'account'],
    'data': [
        'security/security.xml',
        'security/app_group_links.xml',
        'security/ir.model.access.csv',
        'data/classification_data.xml',
        'views/res_partner_classification_views.xml',
        'wizards/res_partner_classification_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/menu_views.xml',
        'views/sale_purchase_account_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'pre_init_hook': 'pre_init_hook',
    'assets': {
        'web.assets_backend': [
            'custom_contacts_manager/static/src/css/contact_category.css',
        ],
    },
}
