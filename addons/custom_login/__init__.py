# -*- coding: utf-8 -*-
from . import models

from odoo.tools import config


def post_load():
    """Disable Odoo's built-in database selector/manager screen.

    That screen (logo + "Manage Databases | Powered by Odoo") is a
    separate core page, not part of this module's /web/login redesign —
    it's what briefly shows before Odoo resolves which database to use
    and redirects to /web/login, which is why it flashes ahead of the
    branded card. Normally you'd turn it off with `list_db = False` in
    odoo.conf, but `post_load` is a standard Odoo hook: any function by
    this name in a module's top-level __init__.py runs once, right after
    the addons registry finishes loading and before any request is
    served — so setting it here has the same effect without needing
    access to the server's config file.

    Safe only for a single-database deployment like this one: it makes
    Odoo require the database to be resolved unambiguously (via
    `dbfilter` or the `-d` startup flag) instead of offering a picker.
    If this server is ever meant to host more than one database, remove
    this override (or delete this file) first.
    """
    config["list_db"] = False
