# NOTE: This file used to contain a second, near-identical copy of the
# `purchase.order` class (same lc_id field, same onchanges, same
# button_confirm override) as models/purchase_order.py. Because both
# files used `_inherit = 'purchase.order'` with the same method names,
# Odoo merged them and the logic ran twice (harmless but wasteful), and
# this file's slightly stricter lc_id domain (state == 'open' only,
# instead of 'open' or 'utilized') silently overrode the intended one.
#
# All Local vs Import / Letter-of-Credit logic now lives in a single
# place: models/purchase_order.py. This file is kept as a placeholder
# (and is no longer imported from models/__init__.py) in case
# purchase.order.line-specific fields are needed here in the future.
