from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    # Relabeling the native field's `string` here changes the label
    # everywhere it's shown (list, form, the receipt serial-assignment
    # popup, etc.) without touching any core view - Odoo pulls the label
    # from the field definition unless a view explicitly overrides it.
    name = fields.Char(string='VIN')

    x_secondary_number = fields.Char(
        string='Serial Number',
        help="Second identifier alongside the VIN.",
    )

    # Plain text snapshot of the Shipment Tracking reference (e.g.
    # "SHP/00012") this unit arrived on, rather than a Many2one, so it
    # displays cleanly for any user (Sales, Inventory, ...) without
    # needing read access to the Shipment & Container Tracking module.
    # Set automatically when a brand new Lot/Serial Number is created
    # while receiving (see stock_move_line.py); editable by hand here
    # for older units or corrections.
    shipment_reference = fields.Char(
        string='Shipment',
        help="Shipment (from Shipment & Container Tracking) this unit "
             "was received on.",
    )

