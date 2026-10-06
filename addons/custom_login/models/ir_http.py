# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _post_dispatch(cls, response):
        """Prevent browser from caching authenticated / webclient pages.

        After logout or session expiry the Back button must not restore a
        previous backend page from the bfcache (which then shows
        "Odoo Session Expired" and RPC 404 errors). We mark those
        responses as non-storeable so the only public view stays /web/login.
        """
        super()._post_dispatch(response)
        try:
            if response is None or not hasattr(response, "headers"):
                return
            path = ""
            if request and getattr(request, "httprequest", None):
                path = request.httprequest.path or ""

            # Everything under the webclient except the login form itself.
            # Also cover JSON-RPC endpoints the backend uses.
            is_webclient = (
                path.startswith("/web")
                or path.startswith("/odoo")
                or path.startswith("/binget")
                or path.startswith("/mail")
                or path.startswith("/discuss")
            )
            is_login = path.startswith("/web/login") or path.startswith("/web/session/logout")

            if is_webclient and not is_login:
                response.headers["Cache-Control"] = (
                    "no-store, no-cache, must-revalidate, max-age=0"
                )
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"

            # When the user lands on login (e.g. after logout), ask the
            # browser to drop cached app data so Back cannot revive an
            # old session page.
            if path.startswith("/web/login"):
                # Clear-Site-Data is supported by modern Chromium/Firefox.
                # Harmless if ignored by older browsers.
                response.headers["Clear-Site-Data"] = '"cache"'
                response.headers["Cache-Control"] = (
                    "no-store, no-cache, must-revalidate, max-age=0"
                )
        except Exception:
            # Never break the response pipeline for a cache header
            pass
