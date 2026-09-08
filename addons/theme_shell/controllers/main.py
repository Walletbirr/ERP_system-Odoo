# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.web.controllers.home import Home


class BingetHome(Home):
    """Adds /binget and /binget/<path:subpath> as extra URLs for the
    exact same webclient bootstrap handler Odoo's core `Home` controller
    already serves at /web, /odoo and /odoo/<path:subpath>.

    NOTE ON WHY THE FULL ORIGINAL URL LIST IS REPEATED BELOW:
    Odoo's controller-inheritance mechanism replaces a parent's route
    list wholesale when a subclass redeclares @http.route on a method of
    the same name — it does not merge the two lists. So every original
    pattern from web/controllers/home.py's `web_client` has to be
    repeated here alongside the new /binget ones, or /web and /odoo/*
    would stop resolving the moment this module is installed.

    This method body only calls straight into the parent implementation
    — no behavior changes, this purely adds URL aliases. The matching
    frontend change (making the router recognize AND build "/binget"
    URLs) lives in
    static/src/core/browser/router_patch.js.
    """

    @http.route(
        [
            "/web",
            "/odoo",
            "/odoo/<path:subpath>",
            "/scoped_app/<path:subpath>",
            "/binget",
            "/binget/<path:subpath>",
        ],
        type="http",
        auth="none",
        readonly=Home._web_client_readonly,
    )
    def web_client(self, s_action=None, **kw):
        response = super().web_client(s_action=s_action, **kw)
        # Rewrite the server-rendered <title> directly in the HTTP
        # response body, instead of via a QWeb inherit of web.layout.
        # A QWeb <template>/ir.ui.view override is NOT usable here:
        # Odoo silently remaps ir.ui.view records to theme.ir.ui.view
        # for any module whose technical name starts with "theme_"
        # (the website theme-preview convention) — this module is
        # named theme_shell, so that remap fires regardless of what
        # the xpath/template actually contains, and blows up on
        # upgrade with KeyError: 'theme.ir.ui.view' if the website
        # app isn't installed. Patching the response bytes here sits
        # entirely outside that mechanism, so it can't trip it.
        # sidebar.js's titleService fix still runs afterward and
        # takes over per-page titles once the app has mounted.
        #
        # IMPORTANT: request.render() (called inside super().web_client())
        # returns a Response whose QWeb template is rendered LAZILY —
        # Odoo's own dispatcher calls response.flatten() to actually
        # render it, and only AFTER this method returns. So at this
        # point response.data is empty and .replace() would be a
        # silent no-op. flatten() here forces the render immediately;
        # it's a no-op if Odoo has already flattened it by the time we
        # get the response (it checks `if self.template:` internally),
        # so this is safe either way.
        if hasattr(response, "flatten"):
            response.flatten()
        if getattr(response, "status_code", None) == 200 and response.data:
            response.data = response.data.replace(
                b"<title>Odoo</title>", b"<title>BINGET</title>"
            )
        return response
