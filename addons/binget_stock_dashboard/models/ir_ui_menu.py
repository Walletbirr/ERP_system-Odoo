# -*- coding: utf-8 -*-
from odoo import models


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def button_immediate_upgrade(self):
        res = super().button_immediate_upgrade()
        if any(m.name == "binget_stock_dashboard" for m in self):
            from odoo.addons.binget_stock_dashboard.hooks import _retarget_product_menus
            _retarget_product_menus(self.env)
        return res
