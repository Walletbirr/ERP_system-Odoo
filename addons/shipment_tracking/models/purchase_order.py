from odoo import models
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_cancel(self):

        for po in self:

            shipments = self.env[
                'shipment.tracking'
            ].search([
                ('purchase_order_id', '=', po.id)
            ])

            shipments._validate_po_cancellation()

        return super().button_cancel()