# -*- coding: utf-8 -*-
{
    "name": "Custom Login Page",
    "summary": "Standalone redesign of the /web/login page only.",
    "description": """
Restyles the Odoo login page (/web/login) with a branded card layout.
Also prevents the browser Back button from restoring internal views
after logout (no more "Odoo Session Expired" dialog).

Deliberately does NOT modify Odoo's login QWeb template: it only loads
CSS/JS into the frontend bundle and a small session guard into the
backend bundle. See VERIFY comments in login.js for selector assumptions.
""",
    "version": "18.0.1.2.0",
    "category": "Theme",
    "author": "Binget Holding plc",
    "license": "LGPL-3",
    "depends": ["web"],
    "assets": {
        "web.assets_frontend": [
            "custom_login/static/src/login/login.js",
            "custom_login/static/src/login/login.scss",
        ],
        "web.assets_backend": [
            "custom_login/static/src/session/session_guard.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
