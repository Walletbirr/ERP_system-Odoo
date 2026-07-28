# -*- coding: utf-8 -*-
from odoo import models, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # If we're being called back by the confirmation wizard, this flag
        # is set - let the real validation run normally.
        if self.env.context.get('skip_validate_confirmation'):
            return super(StockPicking, self).button_validate()

        # Otherwise, this is the user clicking Validate directly on a
        # Receipt, Delivery, or Internal Transfer - interrupt and ask for
        # explicit confirmation first.
        return {
            'name': _('Confirm Validation'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking.validate.confirm',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_picking_ids': [(6, 0, self.ids)]},
        }
