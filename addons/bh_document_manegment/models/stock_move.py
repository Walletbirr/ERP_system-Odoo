from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)
        self._sync_vehicle_document_units_after_delivery()
        return res

    def _sync_vehicle_document_units_after_delivery(self):
        """Auto-backfill VINs on vehicle.document.unit records the moment
        the outgoing delivery behind them is validated, instead of
        requiring someone to remember to click 'Sync VINs' on the
        invoice line by hand.

        Mirrors account.move.line.action_sync_units_button() exactly -
        this just triggers it automatically at the natural moment the
        new information (a delivered lot) becomes available, for every
        sale line whose invoice line(s) still have unassigned units.
        Safe to call on every stock.move done, including ones with
        nothing to do with vehicle tracking: it's a no-op for anything
        that isn't a done outgoing move, or has no unassigned units
        waiting.
        """
        moves = self.filtered(
            lambda m: m.state == 'done'
            and m.picking_type_id.code == 'outgoing'
            and m.sale_line_id
        )
        if not moves:
            return
        invoice_lines = moves.sale_line_id.invoice_lines.filtered(
            lambda l: l.x_is_vehicle_line and l.x_has_unassigned_units
        )
        for line in invoice_lines:
            line.action_sync_units_button()
