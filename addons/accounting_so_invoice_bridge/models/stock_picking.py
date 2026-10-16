from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super()._action_done()
        # sudo: whoever validates the transfer (even a plain stock user)
        # must be able to close the linked stock request.
        requests = self.env['sale.stock.request'].sudo().search([
            ('picking_id', 'in', self.ids), ('state', '=', 'accepted')])
        requests.filtered(
            lambda r: r.picking_id.state == 'done')._mark_done()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        requests = self.env['sale.stock.request'].sudo().search([
            ('picking_id', 'in', self.ids), ('state', '=', 'accepted')])
        requests.filtered(
            lambda r: r.picking_id.state == 'cancel')._transfer_cancelled()
        return res
