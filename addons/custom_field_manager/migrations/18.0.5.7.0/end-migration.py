# -*- coding: utf-8 -*-
"""18.0.5.7.0 — rebuild every applied Field / Tab / Button rule.

This is an ``end-`` migration on purpose: this module only depends on
``base`` and ``mail`` so it is loaded BEFORE accounting, sales, ... during an
upgrade. A ``post-`` script would run while models such as ``account.move``
are not in the registry yet and view validation would fail. ``end-`` scripts
run once every module has been loaded.

Rules applied by 18.0.5.6.x and earlier patched only the FIRST matching
element of a view (e.g. one of the two "Other Info" tabs of Journal Entries,
or the invisible technical copy of a field). They are re-applied here with
the new engine, which patches every match and verifies the merged view.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    rules = env["field.manager.rule"].search([
        ("state", "=", "applied"),
        ("target_type", "in", ("field", "tab", "button")),
    ])
    for rule in rules:
        try:
            with cr.savepoint():
                rule.action_reapply()
            _logger.info("custom_field_manager: re-applied rule #%s (%s)", rule.id, rule.name)
        except Exception:
            _logger.warning(
                "custom_field_manager: could not re-apply rule #%s (%s). "
                "Open it and click 'Re-apply' (or Revert + Apply) manually.",
                rule.id, rule.name, exc_info=True,
            )
