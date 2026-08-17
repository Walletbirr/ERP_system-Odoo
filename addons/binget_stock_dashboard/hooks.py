# -*- coding: utf-8 -*-
"""
Fully automatic install / uninstall — no shell scripts.

Install/Upgrade → Products (Inventory/Sales/Purchase) open premium catalog
Uninstall       → original menus restored; zero footprints
"""

import json
import logging
import re

_logger = logging.getLogger(__name__)

_BACKUP_KEY = "binget_stock_dashboard.menu_action_backup"

_MENU_XMLIDS = (
    "stock.menu_product_variant_config_stock",
    "product.menu_product_template_action",
    "stock.menu_product_template_action",
    "sale.menu_product_template_action",
    "sale.prod_config_main",
    "purchase.menu_procurement_management_product_variant",
    "purchase.product_product_menu",
    "purchase.menu_product_in_config_purchase",
)

_PRODUCT_ACTION_XMLIDS = (
    "product.product_template_action",
    "product.product_template_action_all",
    "stock.product_template_action_product",
    "sale.product_template_action",
    "purchase.product_normal_action_puchased",
)

_OUR_TAGS = ("binget_products_gallery", "binget_stock_dashboard")
_ACTION_RE = re.compile(r"^(ir\.actions\.\w+),(\d+)$")


def _client_ref(env):
    act = env.ref(
        "binget_stock_dashboard.action_binget_products_gallery",
        raise_if_not_found=False,
    )
    return ("ir.actions.client,%s" % act.id) if act else None


def _action_exists(env, action):
    if not action:
        return True
    m = _ACTION_RE.match(str(action).strip())
    if not m:
        return False
    try:
        return bool(env[m.group(1)].sudo().browse(int(m.group(2))).exists())
    except Exception:
        return False


def _default_product_ref(env):
    act = env.ref("product.product_template_action", raise_if_not_found=False)
    return ("ir.actions.act_window,%s" % act.id) if act else False


def _product_action_refs(env):
    refs = set()
    for xid in _PRODUCT_ACTION_XMLIDS:
        act = env.ref(xid, raise_if_not_found=False)
        if act:
            refs.add("ir.actions.act_window,%s" % act.id)
    acts = env["ir.actions.act_window"].sudo().search([
        ("res_model", "=", "product.template"),
        ("name", "ilike", "product"),
    ])
    for a in acts:
        refs.add("ir.actions.act_window,%s" % a.id)
    return refs


def _is_products_menu(menu):
    blob = ("%s %s" % (menu.name or "", menu.complete_name or "")).lower()
    return "product" in blob


def _collect_product_menus(env):
    Menu = env["ir.ui.menu"].sudo()
    menus = Menu.browse()

    for xid in _MENU_XMLIDS:
        m = env.ref(xid, raise_if_not_found=False)
        if m:
            menus |= m

    refs = _product_action_refs(env)
    if refs:
        menus |= Menu.search([("action", "in", list(refs))])

    parent = env.ref("stock.menu_product_variant_config_stock", raise_if_not_found=False)
    if parent:
        menus |= Menu.search([("parent_id", "=", parent.id), ("name", "=", "Products")])

    proot = env.ref("purchase.menu_purchase_root", raise_if_not_found=False)
    if proot:
        menus |= Menu.search([
            ("parent_id", "=", proot.id),
            ("name", "=", "Products"),
            ("active", "=", True),
        ])

    sroot = env.ref("sale.sale_menu_root", raise_if_not_found=False)
    if sroot:
        menus |= Menu.search([
            ("parent_id", "child_of", sroot.id),
            ("name", "=", "Products"),
            ("active", "=", True),
        ])

    return menus.filtered(_is_products_menu)


def _hide_legacy_catalog_menus(env):
    Menu = env["ir.ui.menu"].sudo()
    Menu.search([("name", "=", "Product Catalog")]).write({"active": False})
    for xid in (
        "binget_stock_dashboard.menu_binget_products_catalog",
        "binget_stock_dashboard.menu_binget_inventory_products",
        "binget_stock_dashboard.menu_binget_inventory_products_root",
    ):
        m = env.ref(xid, raise_if_not_found=False)
        if m:
            m.write({"active": False})


def _dedupe_purchase_products(env):
    proot = env.ref("purchase.menu_purchase_root", raise_if_not_found=False)
    if not proot:
        return
    Menu = env["ir.ui.menu"].sudo()
    prods = Menu.search([
        ("parent_id", "=", proot.id),
        ("name", "=", "Products"),
        ("active", "=", True),
    ])
    if len(prods) > 1:
        prods[1:].write({"active": False})
        _logger.info("Binget: hid %s duplicate Purchase Products menu(s)", len(prods) - 1)


def apply_menu_overrides(env):
    """Retarget Products menus → premium catalog. Safe to call multiple times."""
    client_ref = _client_ref(env)
    if not client_ref:
        _logger.error("Binget: catalog client action missing")
        return

    ICP = env["ir.config_parameter"].sudo()
    try:
        backup = json.loads(ICP.get_param(_BACKUP_KEY, "{}") or "{}")
    except Exception:
        backup = {}

    menus = _collect_product_menus(env)
    for menu in menus:
        key = str(menu.id)
        if (
            key not in backup
            and menu.action
            and str(menu.action).startswith("ir.actions.act_window,")
        ):
            backup[key] = menu.action
        if menu.action != client_ref:
            menu.write({"action": client_ref, "active": True})

    ICP.set_param(_BACKUP_KEY, json.dumps(backup))
    _hide_legacy_catalog_menus(env)
    _dedupe_purchase_products(env)
    _logger.info("Binget: retargeted %s Products menu(s) to premium catalog", len(menus))


def post_init_hook(env):
    apply_menu_overrides(env)


def uninstall_hook(env):
    """Restore originals and leave zero footprints."""
    ICP = env["ir.config_parameter"].sudo()
    Menu = env["ir.ui.menu"].sudo()
    Client = env["ir.actions.client"].sudo()
    default_ref = _default_product_ref(env)

    try:
        backup = json.loads(ICP.get_param(_BACKUP_KEY, "{}") or "{}")
    except Exception:
        backup = {}

    for mid, action in backup.items():
        try:
            menu = Menu.browse(int(mid))
        except Exception:
            continue
        if not menu.exists():
            continue
        if action and _action_exists(env, action):
            menu.write({"action": action, "active": True})
        elif default_ref:
            menu.write({"action": default_ref, "active": True})

    our_actions = Client.search([("tag", "in", _OUR_TAGS)])
    our_refs = {"ir.actions.client,%s" % a.id for a in our_actions}
    if our_refs and default_ref:
        Menu.search([("action", "in", list(our_refs))]).write({
            "action": default_ref,
            "active": True,
        })

    proot = env.ref("purchase.menu_purchase_root", raise_if_not_found=False)
    if proot:
        Menu.search([
            ("parent_id", "=", proot.id),
            ("name", "=", "Products"),
            ("active", "=", False),
        ]).write({"active": True})

    if default_ref:
        for menu in Menu.search([("action", "!=", False)]):
            if _action_exists(env, menu.action):
                continue
            if _is_products_menu(menu):
                menu.write({"action": default_ref, "active": True})

    ICP.set_param(_BACKUP_KEY, "{}")
    ICP.search([("key", "like", "binget_stock_dashboard.%")]).unlink()
    _logger.info("Binget: uninstalled — Products restored, footprints cleared")
