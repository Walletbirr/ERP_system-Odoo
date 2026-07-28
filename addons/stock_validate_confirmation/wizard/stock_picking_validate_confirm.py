# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockPickingValidateConfirm(models.TransientModel):
    _name = 'stock.picking.validate.confirm'
    _description = 'Confirm Transfer Validation'

    picking_ids = fields.Many2many('stock.picking', string='Transfers')
    picking_names = fields.Char(compute='_compute_display_info')
    operation_type_names = fields.Char(compute='_compute_display_info')

    @api.depends('picking_ids')
    def _compute_display_info(self):
        for rec in self:
            rec.picking_names = ', '.join(rec.picking_ids.mapped('name'))
            rec.operation_type_names = ', '.join(
                set(rec.picking_ids.mapped('picking_type_id.name'))
            )

    def action_confirm(self):
        """User said Yes - run the real validation."""
        self.ensure_one()
        return self.picking_ids.with_context(skip_validate_confirmation=True).button_validate()

    def action_cancel(self):
        """User said No - just close the dialog, nothing changes."""
        return {'type': 'ir.actions.act_window_close'}
