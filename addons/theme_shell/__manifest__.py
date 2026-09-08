# -*- coding: utf-8 -*-
{
    "name": "Theme Shell - Custom Branded Sidebar",
    "summary": "Replaces the stock Odoo top navbar with a persistent, "
                "brand-colored sidebar (with a green/gold theme toggle).",
    "version": "18.0.1.1.0",
    # VERIFY: "18.0.1.0.0" assumes Odoo 18, carried over from earlier
    # notes in this project ("stable in shape across 16-18"). Adjust the
    # leading version number to match your actual Odoo version if different.
    "category": "Theme",
    "author": "Binget Holding plc",
    "license": "LGPL-3",
    # This does NOT depend on "binget_dashboard", even though the
    # sidebar's notification bell calls straight into that module's
    # binget.dashboard model (get_notifications / mark_notifications_seen
    # / etc., see sidebar.js) and opens its "binget_dashboard" client
    # action for the low-stock drill-down. That's deliberate: those are
    # plain RPC calls by model/action *name*, not a Python import, so no
    # manifest dependency is required for them to work — and
    # binget_dashboard already depends on THIS module (for the sidebar's
    # CSS custom properties, --sb-bg/--sb-accent/etc.). Adding the
    # reverse dependency here previously created A-depends-B-depends-A,
    # which Odoo refuses to install ("Recursion error in modules
    # dependencies!"). If binget_dashboard isn't installed, the bell's
    # RPC calls just fail silently (caught in loadNotifications, etc.)
    # and it shows empty — it doesn't break the sidebar itself.
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            # Patches the router's URL builder/parser to use "/binget"
            # instead of "/odoo", without forking web's router.js.
            # See the file's own header comment for why a full-file
            # replace doesn't work for a module this widely imported.
            "theme_shell/static/src/core/browser/router_patch.js",
            "theme_shell/static/src/sidebar/sidebar.js",
            "theme_shell/static/src/sidebar/sidebar.scss",
            "theme_shell/static/src/sidebar/sidebar.xml",
            "theme_shell/static/src/webclient/webclient_layout.scss",
            "theme_shell/static/src/webclient/global_theme.scss",
            "theme_shell/static/src/transitions/page_transitions.js",
            "theme_shell/static/src/transitions/page_transitions.xml",
            "theme_shell/static/src/transitions/transitions.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
