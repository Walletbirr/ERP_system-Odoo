# -*- coding: utf-8 -*-
from odoo import api, models


class IrActionsClient(models.Model):
    _inherit = "ir.actions.client"

    @api.model
    def _binget_apply_menu_overrides(self):
        """Called from data XML on install/upgrade — retarget Products menus."""
        from odoo.addons.binget_stock_dashboard.hooks import apply_menu_overrides
        apply_menu_overrides(self.env)
        return True
