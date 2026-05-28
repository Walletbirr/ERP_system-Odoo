# /custom_addons/shipment_tracking/models/stock_picking_inherit.py

from odoo import models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """
        Block validation of incoming receipts (purchase receipts) unless:
          1. A shipment linked to the Purchase Order exists and is 'arrived'.
          2. At least one local transport trip for that shipment is 'delivered'.

        Only applies to incoming pickings (purchase receipts) that have a
        linked purchase order. Outgoing/internal transfers are not affected.
        """
        for picking in self:
            # Only check incoming receipts linked to a purchase order
            if picking.picking_type_code != 'incoming':
                continue
            if not picking.purchase_id:
                continue

            po = picking.purchase_id

            # ── 1. Find shipment(s) linked to this PO ─────────────────────
            shipments = self.env['shipment.tracking'].search([
                ('purchase_order_id', '=', po.id),
            ])

            if not shipments:
                raise UserError(_(
                    'Cannot validate receipt for Purchase Order "%s".\n\n'
                    'No shipment has been created for this order yet.\n'
                    'Please create a shipment and complete the full '
                    'Arrived → Local Transport Delivered flow before receiving.'
                ) % po.name)

            # ── 2. Check at least one shipment is arrived ──────────────────
            arrived_shipments = shipments.filtered(
                lambda s: s.state == 'arrived'
            )
            if not arrived_shipments:
                states = ', '.join(
                    dict(self.env['shipment.tracking']._fields['state'].selection).get(s, s)
                    for s in shipments.mapped('state')
                )
                raise UserError(_(
                    'Cannot validate receipt for Purchase Order "%s".\n\n'
                    'The linked shipment(s) have not arrived yet '
                    '(current status: %s).\n'
                    'Products can only be received after the shipment has '
                    'arrived and local transport is fully delivered.'
                ) % (po.name, states))

            # ── 3. Check at least one delivered transport trip exists ───────
            delivered_trips = self.env['local.transport.trip'].search([
                ('shipment_id', 'in', arrived_shipments.ids),
                ('state', '=', 'delivered'),
            ])
            if not delivered_trips:
                # Check if any trip exists at all (for a more helpful message)
                any_trips = self.env['local.transport.trip'].search([
                    ('shipment_id', 'in', arrived_shipments.ids),
                ])
                if not any_trips:
                    raise UserError(_(
                        'Cannot validate receipt for Purchase Order "%s".\n\n'
                        'The shipment has arrived but no local transport trip '
                        'has been created yet.\n'
                        'Please create and complete a local transport trip '
                        '(border → warehouse) before receiving the products.'
                    ) % po.name)
                else:
                    trip_states = ', '.join(
                        dict(self.env['local.transport.trip']._fields['state'].selection).get(s, s)
                        for s in any_trips.mapped('state')
                    )
                    raise UserError(_(
                        'Cannot validate receipt for Purchase Order "%s".\n\n'
                        'Local transport has not been fully delivered yet '
                        '(current trip status: %s).\n'
                        'Products can only be received after all containers '
                        'have been delivered to the warehouse.'
                    ) % (po.name, trip_states))

        # All checks passed — proceed with normal validation
        return super().button_validate()
