"""Pre-migration: drop stale custom views before the new module data
loads.

Why this exists: when a view-referenced field is renamed/removed in a
new module version (e.g. target_tax_percent -> target_tax_id in
2.2.0), Odoo reloads the Python model BEFORE re-writing the view XML
records. The OLD view still stored in the database from the previous
install still points at the now-missing field, and Odoo's view
validation fails on that stale record before it ever gets to load the
corrected XML. Deleting the old view records here, before data load,
avoids that chicken-and-egg failure - the upgrade then recreates them
fresh from the current XML with no dangling field references.

Safe to run on any install state: uses env.ref(raise_if_not_found=False)
so it's a no-op if the views don't exist (e.g. fresh install).
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    xml_ids = [
        'price_bracket_pricelist.view_product_pricelist_item_form_bracket_hint',
        'price_bracket_pricelist.view_product_pricelist_item_form_tax_included_target',
    ]
    for xml_id in xml_ids:
        view = env.ref(xml_id, raise_if_not_found=False)
        if view:
            view.unlink()
