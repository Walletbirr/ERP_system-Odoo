# -*- coding: utf-8 -*-
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from odoo import http
from odoo.addons.web.controllers.home import Home
from odoo.http import request

# Matches a leading "/odoo" path segment, either at the very start of a
# relative path ("/odoo", "/odoo/action-1", "/odoo?debug=1") or right
# after a scheme+host in an absolute URL ("http://host:8069/odoo") —
# never a path that merely starts with those letters (e.g.
# "/odoo_something"). Mirrors the /odoo <-> /binget translation
# static/src/core/browser/router_patch.js already does on the client.
_ODOO_SEGMENT_RE = re.compile(r"(^|://[^/]+)/odoo(?=$|[/?#])")


def _odoo_path_to_binget(path):
    """Rewrite a leading "/odoo" path segment to "/binget" in a relative
    path or absolute URL, leaving everything else (subpath, query
    string, fragment, scheme/host) untouched. Returns the input
    unchanged if no such segment is found.
    """
    if not path:
        return path
    return _ODOO_SEGMENT_RE.sub(r"\1/binget", path, count=1)


def _rewrite_odoo_refs_in_url(url):
    """Like _odoo_path_to_binget, but also looks INSIDE a "redirect"
    query parameter, not just the bare path.

    Needed because "/odoo" shows up in two different shapes depending
    on which controller built the URL:
      - as the path itself: Location: /odoo
      - url-encoded as a query value: Location: /web/login?redirect=%2Fodoo%3F
        (this is what Home.web_client's own internal not-logged-in
        check builds when auth='none' lets it handle that case itself
        instead of the framework's generic auth redirect — it's a
        302/303, so _retitle's status_code==200 guard never sees it,
        and the plain path-only helper above never looked inside the
        query string to begin with).
    Both need translating so "/odoo" never resurfaces anywhere in the
    login round-trip, however it got there.
    """
    if not url:
        return url
    parts = urlsplit(url)
    path = _odoo_path_to_binget(parts.path) if parts.path else parts.path
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    pairs = [
        (k, _odoo_path_to_binget(v) if k == "redirect" else v) for k, v in pairs
    ]
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(pairs), parts.fragment))


def _debinget_redirect(response):
    """If `response` is a redirect (has a Location header, any status
    code), rewrite any "/odoo" reference in it to "/binget". No-op for
    non-redirect responses. Safe to call unconditionally.
    """
    location = getattr(response, "headers", {}).get("Location") if hasattr(response, "headers") else None
    if location:
        response.headers["Location"] = _rewrite_odoo_refs_in_url(location)
    return response


def _retitle(response):
    """Force-render a lazy QWeb Response and swap Odoo's default
    <title>Odoo</title> for <title>BINGET</title> in the raw bytes.

    request.render() returns a Response whose template is rendered
    LAZILY — Odoo's own dispatcher calls response.flatten() to
    actually render it, and only AFTER the controller method
    returns. So response.data is empty until flatten() runs; calling
    it here forces the render immediately. It's a no-op if Odoo has
    already flattened the response by the time we get it (flatten()
    checks `if self.template:` internally), so this is safe either
    way, for both web_client and web_login.
    """
    if hasattr(response, "flatten"):
        response.flatten()
    if getattr(response, "status_code", None) == 200 and response.data:
        response.data = response.data.replace(
            b"<title>Odoo</title>", b"<title>BINGET</title>"
        )
    return response


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
        # Redirect the bare "/odoo" alias straight to its "/binget"
        # equivalent at the HTTP level, before anything is rendered —
        # this is what closes the ~1s flash the client-side fix in
        # router_patch.js couldn't fully avoid. That fix runs via JS
        # AFTER the browser has already painted "/odoo" in the address
        # bar and finished loading/parsing the JS bundle, so there was
        # always some visible window (worse right after Odoo's own
        # post-upgrade reload, which lands here as a genuine fresh
        # "/odoo" page load, not a router transition it could
        # intercept). A server-side redirect resolves before the
        # browser paints anything at all — no JS execution time is in
        # the critical path anymore. /binget itself still flows
        # through the rest of this same method, unaffected; this only
        # short-circuits when "/odoo" specifically was requested.
        path = request.httprequest.path or ""
        if path == "/odoo" or path.startswith("/odoo/"):
            target = "/binget" + path[len("/odoo"):]
            query = request.httprequest.query_string.decode("utf-8")
            if query:
                target += "?" + query
            return request.redirect(target, code=303, local=True)

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
        #
        # NOT-LOGGED-IN CASE: this route runs with auth="none" so it can
        # handle that itself rather than relying on the framework's
        # generic auth redirect — when there's no session, it returns
        # its own 302/303 to /web/login?redirect=<this path>. By this
        # point "/odoo" has already been redirected away above, so the
        # only path that reaches here is "/binget" (or /web) — but
        # Odoo's own redirect-building code still hardcodes "/odoo" as
        # its default target internally in some cases, independent of
        # which alias was actually requested, so this still needs the
        # same rewrite as web_login's redirect below.
        return _retitle(_debinget_redirect(response))

    # VERIFY: this signature (route args, kwargs) mirrors Odoo 18's
    # web/controllers/home.py Home.web_login exactly as of this
    # writing. Controller inheritance replaces the parent's route
    # list wholesale on override (see note on web_client above), so
    # if a future Odoo point release changes this method's signature
    # or added kwargs, this override needs to be updated to match —
    # it isn't auto-inherited.
    @http.route("/web/login", type="http", auth="none", sitemap=False)
    def web_login(self, redirect=None, **kw):
        # The /web/login page is served by this separate route/method
        # (not web_client above), so it needs its own retitle pass —
        # that's the tab still reading "Odoo" on the login screen.
        #
        # Also translate the redirect target so it never routes through
        # "/odoo" — e.g. hitting /binget/apps while logged out bounces
        # here as /web/login?redirect=%2Fodoo%3F (Odoo's own auth guard
        # echoes back whatever path it originally computed, and that's
        # still "/odoo" by default, independent of which alias you
        # actually visited). We rewrite it on the way in, so Odoo builds
        # the post-login redirect against "/binget" instead.
        redirect = _odoo_path_to_binget(redirect)
        response = super().web_login(redirect=redirect, **kw)
        # Belt-and-suspenders: if Odoo computed its own default target
        # internally (redirect was None) rather than using the kwarg
        # above, catch it here on the way out too.
        return _retitle(_debinget_redirect(response))
