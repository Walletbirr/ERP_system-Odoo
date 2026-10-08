{
    'name': 'Binget Stock Dashboard',
    'version': '18.0.3.20.0',
    'summary': 'Premium Stock dashboard + unified Products catalog (auto install & clean uninstall)',
    'description': """
Install (Apps → Activate)
-------------------------
* Inventory → Stock : premium stock dashboard (above Reporting)
* Inventory / Sales / Purchase → Products : same premium catalog
* No extra tabs, no shell scripts

Uninstall (Apps → Uninstall)
----------------------------
* Restores original Products menu actions from backup
* System returns to standard Odoo Products pages
* No leftover broken menus
""",
    'category': 'Inventory/Inventory',
    'author': 'Binget Holding',
    'depends': ['stock', 'product', 'web', 'base_import'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_dashboard_menu.xml',
        'views/product_kanban_views.xml',
        'views/product_safe_form.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'binget_stock_dashboard/static/src/scss/stock_dashboard.scss',
            'binget_stock_dashboard/static/src/scss/products_gallery.scss',
            'binget_stock_dashboard/static/src/scss/import_cog.scss',
            'binget_stock_dashboard/static/src/js/import_cog.js',
            'binget_stock_dashboard/static/src/js/stock_dashboard.js',
            'binget_stock_dashboard/static/src/js/products_gallery.js',
            'binget_stock_dashboard/static/src/xml/stock_dashboard.xml',
            'binget_stock_dashboard/static/src/xml/products_gallery.xml',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
