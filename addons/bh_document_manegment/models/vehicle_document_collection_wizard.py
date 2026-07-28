from datetime import datetime

from odoo import api, fields, models


class VehicleDocumentCollectionWizard(models.TransientModel):
    _name = 'vehicle.document.collection.wizard'
    _description = 'Confirm Vehicle Document Collection'

    unit_id = fields.Many2one(
        'vehicle.document.unit', required=True, readonly=True,
    )
    product_id = fields.Many2one(
        related='unit_id.product_id', string='Vehicle', readonly=True,
    )
    product_model = fields.Char(
        related='product_id.product_tmpl_id.product_model',
        string='Product Model', readonly=True,
    )
    unit_value = fields.Float(
        related='unit_id.unit_price', string='Amount', readonly=True,
    )
    shipment_reference = fields.Char(
        related='lot_id.shipment_reference', string='Shipment', readonly=True,
        help="Shipment (from Shipment & Container Tracking) this specific "
             "unit was received on.",
    )
    collection_date = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self),
    )
    dealer_id = fields.Many2one(
        'res.partner', string='Dealer/Customer', required=True,
        help="Defaults to the invoice's customer - change only if a "
             "different representative is collecting on their behalf.",
    )
    lot_id = fields.Many2one(
        'stock.lot', string='VIN', required=True,
        domain="[('id', 'in', available_lot_ids)]",
        help="Auto-matched from the sale order's delivery when possible. "
             "Only lots that were actually delivered for this line, and "
             "aren't already claimed by another unit, can be picked here - "
             "this prevents assigning a VIN that belongs to a different "
             "customer's unit of the same product.",
    )
    available_lot_ids = fields.Many2many(
        'stock.lot', compute='_compute_available_lot_ids',
    )
    x_lot_prematched = fields.Boolean(
        compute='_compute_x_lot_prematched',
        help="True if the unit already had a VIN auto-matched from the "
             "delivery before this wizard was opened. Keeps the VIN field "
             "read-only in that case, since there's nothing to pick - it "
             "only stays editable for units that still need a VIN "
             "assigned by hand.",
    )
    x_secondary_number_display = fields.Char(
        related='lot_id.x_secondary_number', string='Serial Number',
        readonly=True,
    )
    collector_name = fields.Char(string="Collector's Name", required=True)
    x_collected_number = fields.Char(
        string='Number (How Much?)', default='1', readonly=True,
        help="This wizard always collects exactly one document, so "
             "this is fixed at 1. To record several documents picked "
             "up together, use 'Collect Multiple Documents (by VIN)' "
             "instead.",
    )
    collector_phone = fields.Char(string='Phone Number', required=True)
    x_is_dealer_collector = fields.Boolean(
        string='Dealer/Customer Collected',
        help="Tick this if the Dealer is picking up the document "
             "themselves, rather than sending a representative. "
             "Collector's Name and Phone Number are then filled in from "
             "the Dealer's own profile and locked.",
    )
    id_document_type = fields.Many2one(
        'vehicle.id.document.type', string='ID Document Type',
    )
    id_document = fields.Binary(string='ID Document (Image or PDF)')
    id_document_filename = fields.Char()

    @api.depends('unit_id')
    def _compute_x_lot_prematched(self):
        for wiz in self:
            wiz.x_lot_prematched = bool(wiz.unit_id.lot_id)

    @api.onchange('x_is_dealer_collector', 'dealer_id')
    def _onchange_x_is_dealer_collector(self):
        for wiz in self:
            if wiz.x_is_dealer_collector and wiz.dealer_id:
                wiz.collector_name = wiz.dealer_id.name
                wiz.collector_phone = wiz.dealer_id.phone or wiz.dealer_id.mobile

    @api.depends('unit_id')
    def _compute_available_lot_ids(self):
        for wiz in self:
            unit = wiz.unit_id
            if not unit:
                wiz.available_lot_ids = False
                continue
            free_lots = unit.move_line_id._get_free_delivered_lots()
            # _get_free_delivered_lots() excludes every lot already
            # claimed by ANY unit, including this one's own current
            # lot_id - add it back so re-confirming the same VIN, or
            # switching away and back, both stay possible.
            lots = self.env['stock.lot'].browse([l.id for l in free_lots])
            if unit.lot_id:
                lots |= unit.lot_id
            wiz.available_lot_ids = lots

    def action_confirm(self):
        self.ensure_one()
        collected_dt = datetime.combine(
            self.collection_date, fields.Datetime.now().time()
        )
        collector_vals = {
            'x_document_collected_date': collected_dt,
            'x_collector_dealer_id': self.dealer_id.id,
            'x_collector_name': self.collector_name,
            'x_collected_number': self.x_collected_number,
            'x_collector_phone': self.collector_phone,
            'lot_id': self.lot_id.id,
        }
        if self.id_document:
            collector_vals['x_id_document'] = self.id_document
            collector_vals['x_id_document_filename'] = self.id_document_filename
            collector_vals['x_id_document_type'] = self.id_document_type.id
        self.unit_id._apply_collection(collector_vals)
        return {'type': 'ir.actions.act_window_close'}