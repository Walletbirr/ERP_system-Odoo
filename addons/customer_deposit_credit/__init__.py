from . import models


def post_init_hook(env):
    """Move the 'Customer Deposits' menu inside the Sales > Reporting submenu.

    We search by name instead of hardcoding an external id, since the exact
    xmlid of the Reporting submenu can vary slightly between Odoo builds /
    localizations. Falls back to leaving it under the Sales root if no
    'Reporting' submenu is found.
    """
    Menu = env['ir.ui.menu']
    our_menu = env.ref('customer_deposit_credit.menu_customer_deposit_root', raise_if_not_found=False)
    sales_root = env.ref('sale.sale_menu_root', raise_if_not_found=False)
    if not our_menu or not sales_root:
        return

    reporting_menu = Menu.search([
        ('parent_id', '=', sales_root.id),
        ('name', '=', 'Reporting'),
    ], limit=1)

    if reporting_menu:
        our_menu.write({'parent_id': reporting_menu.id})
