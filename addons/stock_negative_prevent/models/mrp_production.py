from odoo import models, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def action_confirm(self):
        """
        Override MO confirm to block when any component has insufficient
        stock in its source location.
        """
        for production in self:
            insufficient = []

            for move in production.move_raw_ids.filtered(
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
                        f"Required {demanded:.2f} {move.product_uom.name}, "
                        f"Available {available:.2f} {move.product_uom.name} "
                        f"in [{location.complete_name}]"
                    )

            if insufficient:
                lines = "\n".join(insufficient)
                raise UserError(
                    _(
                        "Cannot confirm Manufacturing Order — insufficient stock "
                        "for the following component(s):\n\n%s\n\n"
                        "Please ensure all components are in stock before "
                        "confirming the manufacturing order."
                    ) % lines
                )

        return super().action_confirm()
