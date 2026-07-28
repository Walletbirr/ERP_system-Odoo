from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    # Mirrors stock.lot's x_secondary_number so the same "VIN + Serial
    # Number" pair used in the Vehicle VIN / Serial Registry (Sales) and
    # on the Lot/Serial form is also available right here, on the
    # "Detailed Operations" screen used while receiving.
    x_lot_secondary_number = fields.Char(
        string='Serial Number',
        help="Second identifier alongside the VIN/Lot Number. If this "
             "line creates a brand new Lot/Serial Number (typical when "
             "receiving), the value entered here is copied onto that new "
             "Lot/Serial Number automatically. If it is linked to an "
             "existing Lot/Serial Number, editing it here updates that "
             "record's Serial Number as well.",
    )

    @api.onchange('lot_id')
    def _onchange_lot_id_x_lot_secondary_number(self):
        # When an existing Lot/Serial Number is picked, show its Serial
        # Number here instead of leaving the column blank.
        for line in self:
            if line.lot_id:
                line.x_lot_secondary_number = line.lot_id.x_secondary_number

    def _get_incoming_shipment(self):
        """Best-effort lookup of the Shipment Tracking record (from the
        Shipment & Container Tracking module) that brought this line's
        product in, based on the purchase order behind the receipt.
        Returns an empty 'shipment.tracking' recordset if none is found.
        """
        self.ensure_one()
        po = self.picking_id.purchase_id
        if not po:
            return self.env['shipment.tracking']
        # Prefer an Arrived shipment (the one that was actually allowed
        # to be received, per the Shipment Tracking receipt gate); fall
        # back to any shipment linked to the PO otherwise.
        shipment = self.env['shipment.tracking'].search([
            ('purchase_order_id', '=', po.id),
            ('state', '=', 'arrived'),
        ], limit=1)
        if not shipment:
            shipment = self.env['shipment.tracking'].search([
                ('purchase_order_id', '=', po.id),
            ], limit=1)
        return shipment

    def _prepare_new_lot_vals(self):
        # Called (one record at a time) when a brand new Lot/Serial
        # Number is created from a typed lot_name, e.g. while validating
        # a receipt. Carry the Serial Number typed on the move line, and
        # the Shipment this unit arrived on, over to the new stock.lot
        # record.
        vals = super()._prepare_new_lot_vals()
        if self.x_lot_secondary_number:
            vals['x_secondary_number'] = self.x_lot_secondary_number
        shipment = self._get_incoming_shipment()
        if shipment:
            vals['shipment_reference'] = shipment.reference
        return vals

    def write(self, vals):
        res = super().write(vals)
        if 'x_lot_secondary_number' in vals:
            for line in self:
                if line.lot_id and line.lot_id.x_secondary_number != line.x_lot_secondary_number:
                    line.lot_id.x_secondary_number = line.x_lot_secondary_number
        return res
