# -*- coding: utf-8 -*-
{
    "name": "Binget Custom Dashboard",
    "summary": "Role-based ERP dashboard (Sales / Inventory / Finance / "
                "Operations) that replaces the default Dashboards app, "
                "styled to match the Binget sidebar theme.",
    "version": "18.0.10.0.0",
    "category": "Reporting",
    "author": "Binget Holding plc",
    "license": "LGPL-3",
    # VERIFY: depends on 'theme_shell' so this module can't be installed
    # without it — the dashboard's CSS relies entirely on the CSS custom
    # properties (--sb-bg, --sb-accent, etc.) that theme_shell's
    # sidebar.scss defines on :root/body. Also depends on 'sale', 'stock',
    # and 'account' since the dashboard queries sale.order, stock.quant,
    # and account.move — if any of those apps aren't actually installed
    # on your database, remove that dependency and the corresponding
    # section in models/dashboard.py, or the relevant RPC call will error.
    "depends": ["web", "sale", "stock", "account", "purchase", "theme_shell"],
    "data": [
        "security/ir.model.access.csv",
        "views/dashboard_menu.xml",
        "views/dashboard_role_views.xml",
        "views/res_users_views.xml",
        "report/activity_report.xml",
    ],
    "post_init_hook": "post_init_hook",
    "assets": {
        "web.assets_backend": [
            # VERIFY: this is Odoo's own bundled Chart.js library path —
            # my best-confidence recollection, not a guarantee. If the
            # dashboard.js console-errors with "Chart is not defined",
            # this path is wrong for your version; search your Odoo
            # install for the actual chart.js/Chart.js file location and
            # swap it in here.
            "web/static/lib/Chart/Chart.js",
            "binget_dashboard/static/src/dashboard/dashboard.js",
            "binget_dashboard/static/src/dashboard/dashboard.xml",
            "binget_dashboard/static/src/dashboard/dashboard.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
