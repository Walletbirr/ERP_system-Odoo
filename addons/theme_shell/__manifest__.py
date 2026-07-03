# -*- coding: utf-8 -*-
{
    "name": "Theme Shell - Custom Branded Sidebar",
    "summary": "Replaces the stock Odoo top navbar with a persistent, "
                "brand-colored sidebar (with a green/gold theme toggle).",
    "version": "18.0.1.0.0",
    # VERIFY: "18.0.1.0.0" assumes Odoo 18, carried over from earlier
    # notes in this project ("stable in shape across 16-18"). Adjust the
    # leading version number to match your actual Odoo version if different.
    "category": "Theme",
    "author": "Binget Holding plc",
    "license": "LGPL-3",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "theme_shell/static/src/sidebar/sidebar.js",
            "theme_shell/static/src/sidebar/sidebar.scss",
            "theme_shell/static/src/sidebar/sidebar.xml",
            "theme_shell/static/src/webclient/webclient_layout.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
