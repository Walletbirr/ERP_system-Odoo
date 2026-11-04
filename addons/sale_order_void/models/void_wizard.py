from odoo import _, api, fields, models


class SaleOrderVoidWizard(models.TransientModel):
    _name = 'sale.order.void.wizard'
    _description = 'Void Sale'

    order_id = fields.Many2one('sale.order', required=True, readonly=True)
    summary = fields.Text(compute='_compute_summary', readonly=True)
    reason = fields.Text(string='Reason', required=True)

    @api.depends('order_id')
    def _compute_summary(self):
        for wizard in self:
            wizard.summary = (
                wizard.order_id.sudo()._void_summary() if wizard.order_id else '')

    def action_confirm(self):
        self.ensure_one()
        self.order_id._void_execute(self.reason)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
