# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Existing databases: relabel "Service Charge" -> "Other Income"."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.custom_invoice_management_sale.hooks import rename_service_charge_product
    rename_service_charge_product(env)
