# -*- coding: utf-8 -*-
{
    "name": "Custom Login Page",
    "summary": "Standalone split-screen redesign of the /web/login page only.",
    "description": """
Restyles the Odoo login page (/web/login) with a split-screen layout:
a dark branded panel on one side, the actual login form on the other.

Deliberately standalone — independent of theme_shell (or any other
theme module), no shared assets, no shared bundle, no dependency on
it. Installing/uninstalling this has zero effect on the backend UI.

Deliberately does NOT modify Odoo's login QWeb template or the login
form's own markup at all: it only loads a CSS file and a small JS file
into the existing "web.assets_frontend" bundle. The JS repositions
elements at runtime (wraps them, adds classes) rather than touching
the authentication form's inputs/structure, and does nothing at all if
its selector guesses don't match your Odoo version — worst case is
"looks like stock Odoo login", never a broken login page. See the
VERIFY comments in login.js / login.scss for exactly which selectors
are assumptions vs. guaranteed-stable.
""",
    "version": "18.0.1.0.0",
    "category": "Theme",
    "author": "Binget Holding plc",
    "license": "LGPL-3",
    "depends": ["web"],
    "assets": {
        "web.assets_frontend": [
            "custom_login/static/src/login/login.js",
            "custom_login/static/src/login/login.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
