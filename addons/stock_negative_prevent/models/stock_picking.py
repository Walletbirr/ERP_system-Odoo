from odoo import models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """
        Override validate to block Internal Transfers when source
        location does not have enough stock for any move line.
        """
        for picking in self:
            # Only check Internal Transfers
            if picking.picking_type_code != 'internal':
                continue

            insufficient = []

            for move in picking.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            ):
                product = move.product_id
                location = move.location_id
                demanded = move.product_uom_qty

                # Get available quantity at the source location
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location.id),
                ], limit=1)

                available = quant.quantity if quant else 0.0

                if available < demanded:
                    insufficient.append(
                        f"• {product.display_name}: "
                        f"Demanded {demanded:.2f} {move.product_uom.name}, "
                        f"Available {available:.2f} {move.product_uom.name} "
                        f"in [{location.complete_name}]"
                    )

            if insufficient:
                lines = "\n".join(insufficient)
                raise UserError(
                    _(
                        "Cannot validate transfer — insufficient stock for the "
                        "following product(s):\n\n%s\n\n"
                        "Please purchase or receive the missing stock before "
                        "performing this internal transfer."
                    ) % lines
                )

        return super().button_validate()

    def action_confirm(self):
        """
        Also check on 'Mark as Todo' / confirm stage for early warning,
        but only raise a hard block on validate (above).
        This keeps the UX consistent — warning on confirm, hard stop on validate.
        """
        return super().action_confirm()
