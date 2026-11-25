from odoo import models, fields
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_import = fields.Boolean(
        string="Import Purchase (Letter of Credit)",
        default=False,
        help="Check this box for purchases from abroad that go through "
             "shipment tracking (and, if the lc_management app is "
             "installed, a Letter of Credit). Leave unchecked for local "
             "purchases, which skip shipment tracking and receive normally."
    )

    def button_cancel(self):

        for po in self:

            shipments = self.env[
                'shipment.tracking'
            ].search([
                ('purchase_order_id', '=', po.id)
            ])

            shipments._validate_po_cancellation()

        return super().button_cancel()