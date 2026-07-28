from odoo import fields, models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    x_lot_secondary_number = fields.Char(
        related='lot_id.x_secondary_number', string='Serial Number',
        store=True,
    )

    x_lot_shipment_reference = fields.Char(
        related='lot_id.shipment_reference', string='Shipment',
        store=True,
    )
