from . import models


_DEFAULT_DASHBOARD_ROLES = [
    # (name, code, sequence, description)
    ("Full Access (Admin)", "admin", 0, "Sees every dashboard section, every branch."),
    ("Sales Person", "sales", 10, ""),
    ("Purchase Officer", "purchase", 20, ""),
    ("Inventory Manager", "inventory", 30, ""),
    ("Accountant / Finance", "accounting", 40, ""),
    ("HR / Workforce", "hr", 50, ""),
    ("Manufacturing", "manufacturing", 60, ""),
]


def _ensure_default_dashboard_roles(env):
    """Seed the starter dashboard roles idempotently.

    Deliberately NOT done as static XML data: a prior failed install
    attempt (on any Odoo version, for any reason — an invalid view tag,
    a network hiccup, whatever) can leave these rows committed in the
    database without Odoo's usual xmlid bookkeeping tracking them as
    "already handled". The next install attempt then tries to CREATE
    them again from scratch and hits the name-uniqueness constraint,
    crashing the whole install over what is really just leftover data.

    Searching for an existing match (by code first, then by name) before
    ever calling create() sidesteps that entirely: whatever state the
    database is already in, re-running this is always safe.
    """
    Role = env["binget.dashboard.role"].sudo()
    for name, code, sequence, description in _DEFAULT_DASHBOARD_ROLES:
        existing = Role.search([("code", "=", code)], limit=1) or Role.search([("name", "=", name)], limit=1)
        if existing:
            continue
        Role.create({"name": name, "code": code, "sequence": sequence, "description": description})


def post_init_hook(env):
    """Deactivates any other pre-existing top-level app menu literally
    named "Dashboard(s)" so this module becomes the single dashboard
    entry point instead of sitting alongside a duplicate.

    Deliberately done by NAME search rather than a hardcoded external
    ID (e.g. 'spreadsheet_dashboard.some_action_id') — guessing the
    wrong XML id for a module we don't control could otherwise raise an
    install-blocking error. If nothing matching is found (already
    removed, or your install doesn't have one), this simply does
    nothing — safe either way, and fully reversible: reactivate the old
    menu anytime via Settings -> Technical -> Menu Items.

    VERIFY: post_init_hook's exact call signature (env directly, vs the
    older (cr, registry) form) differs across Odoo versions. This uses
    the newer single `env` argument form. If module installation fails
    specifically at this hook, check the container logs the same way
    we diagnosed the is_locked error — the traceback will show clearly
    whether it's a signature mismatch, and the fix is a one-line change
    to this function's parameters.
    """
    our_menu = env.ref("binget_dashboard.menu_binget_dashboard_root", raise_if_not_found=False)
    domain = [("parent_id", "=", False), ("name", "=ilike", "dashboard%")]
    if our_menu:
        domain.append(("id", "!=", our_menu.id))
    other_dashboard_menus = env["ir.ui.menu"].search(domain)
    if other_dashboard_menus:
        other_dashboard_menus.write({"active": False})

    _ensure_default_dashboard_roles(env)
