from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def write(self, vals):
        res = super().write(vals)
        if 'cim_reference' in vals or 'client_order_ref' in vals:
            self._direct_cogs_refresh_entry_refs()
        return res

    def _direct_cogs_refresh_entry_refs(self):
        """The CSI may be typed or corrected after the goods were delivered:
        refresh the Reference text (only) of this order's COGS entries."""
        for order in self:
            moves = order.sudo().picking_ids.move_ids
            entries = self.env['account.move'].sudo().search(
                [('stock_move_id', 'in', moves.ids)])
            for entry in entries:
                stock_move = entry.stock_move_id
                if stock_move._is_direct_cogs_move():
                    new_ref = stock_move._direct_cogs_ref(order)
                    if entry.ref != new_ref:
                        entry.ref = new_ref
