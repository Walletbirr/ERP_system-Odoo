from odoo import models


class ShipmentTracking(models.Model):
    _inherit = 'shipment.tracking'

    def action_set_arrived_at_destination(self):
        res = super().action_set_arrived_at_destination()

        for rec in self:
            po = rec.purchase_order_id
            if not po or not po.lc_id:
                continue

            lc = po.lc_id
            if lc.state in ('closed', 'cancelled'):
                continue

            line = lc._create_draft_settlement_line_for_shipment(po, rec)
            if line:
                rec.message_post(
                    body=(
                        f"LC Settlement draft line created for {lc.name} "
                        f"(Purchase Order {po.name}). Review and confirm it from "
                        f"the LC's Settlement tab."
                    )
                )

        return res
