from odoo import _, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_create_invoice(self):
        # Skip the check if the user already confirmed via the warning wizard.
        if self.env.context.get('skip_shipment_check'):
            return super().action_create_invoice()

        # Collect orders that have linked shipments but none arrived yet.
        orders_needing_warning = self.env['purchase.order']
        warning_lines = []

        for order in self:
            shipments = self.env['shipment.tracking'].search([
                ('purchase_order_id', '=', order.id),
            ])

            if not shipments:
                # No shipment linked — no restriction, proceed normally.
                continue

            arrived = shipments.filtered(lambda s: s.state == 'arrived')
            if arrived:
                # At least one shipment arrived — this order is fine.
                continue

            # Has shipments but none arrived yet — needs warning.
            orders_needing_warning |= order
            for s in shipments:
                warning_lines.append(
                    '• %s  [%s]  →  %s' % (
                        s.reference,
                        order.name,
                        dict(s._fields['state'].selection).get(s.state, s.state),
                    )
                )

        if not orders_needing_warning:
            # All orders either have no shipments or have an arrived one.
            return super().action_create_invoice()

        # Build warning message.
        message = _(
            "The following Purchase Order(s) have no shipment that has arrived "
            "at the final destination yet:\n\n"
            "%(lines)s\n\n"
            "You can wait for the shipment to arrive, or proceed anyway to "
            "create the bill now.",
            lines='\n'.join(warning_lines),
        )

        wizard = self.env['shipment.bill.warning.wizard'].create({
            'purchase_order_ids': [(6, 0, orders_needing_warning.ids)],
            'warning_message': message,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Shipment Not Yet Arrived'),
            'res_model': 'shipment.bill.warning.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
