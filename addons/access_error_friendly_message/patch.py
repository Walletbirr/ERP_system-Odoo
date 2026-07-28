# -*- coding: utf-8 -*-
"""
Odoo turns every exception raised while handling a request into the popup
you see in the browser. AccessError is what gets raised when a user's
security groups don't permit an action - by default its message includes
internal details (model name, list of groups that DO have access). We
replace that with a clean, generic message instead.

Where this hook lives has changed across Odoo versions:
  - Odoo <= 16: odoo.http.JsonRequest._handle_exception(self, exception)
  - Odoo >= 17: odoo.http.<Dispatcher>.handle_error(self, exc)
    (JsonRPCDispatcher handles backend RPC calls; HttpDispatcher handles
    plain HTTP routes such as portal/website pages)

This patches whichever one actually exists on the running server, so the
same module works across versions without editing code.
"""
import logging

from odoo.exceptions import AccessError
from odoo.tools.translate import _
import odoo.http as http

_logger = logging.getLogger(__name__)

def _friendly_message():
    # Built lazily (only when actually needed, i.e. inside a real request)
    # rather than at module import time - calling _() at import time is
    # what caused the "no translation language detected" warning in the
    # server log, since there's no active request/language yet at that point.
    return _(
        "You don't have permission to do this. "
        "Please contact your administrator if you believe this is a mistake."
    )


def _swap_message_if_access_error(exc):
    if isinstance(exc, AccessError):
        _logger.info("Access denied (original message): %s", exc.args[0] if exc.args else exc)
        return AccessError(_friendly_message())
    return exc


patched_any = False

# --- Odoo 17+ : Dispatcher.handle_error ---
for dispatcher_name in ('JsonRPCDispatcher', 'HttpDispatcher'):
    dispatcher_cls = getattr(http, dispatcher_name, None)
    if dispatcher_cls is not None and hasattr(dispatcher_cls, 'handle_error'):
        _original_handle_error = dispatcher_cls.handle_error

        def _make_patched_handle_error(original):
            def _patched_handle_error(self, exc):
                exc = _swap_message_if_access_error(exc)
                return original(self, exc)
            return _patched_handle_error

        dispatcher_cls.handle_error = _make_patched_handle_error(_original_handle_error)
        patched_any = True
        _logger.info("access_error_friendly_message: patched %s.handle_error", dispatcher_name)

# --- Odoo <= 16 : JsonRequest._handle_exception ---
_json_request_cls = getattr(http, 'JsonRequest', None)
if _json_request_cls is not None and hasattr(_json_request_cls, '_handle_exception'):
    _original_handle_exception = _json_request_cls._handle_exception

    def _patched_handle_exception(self, exception):
        exception = _swap_message_if_access_error(exception)
        return _original_handle_exception(self, exception)

    _json_request_cls._handle_exception = _patched_handle_exception
    patched_any = True
    _logger.info("access_error_friendly_message: patched JsonRequest._handle_exception")

if not patched_any:
    _logger.warning(
        "access_error_friendly_message: could not find a known exception "
        "handling hook in odoo.http on this Odoo version - module has no effect. "
        "Please report your Odoo version so the patch can be updated."
    )
