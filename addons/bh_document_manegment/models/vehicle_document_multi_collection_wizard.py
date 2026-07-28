from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError


class VehicleDocumentMultiCollectionWizard(models.TransientModel):
    _name = 'vehicle.document.multi.collection.wizard'
    _description = 'Confirm Document Collection for Multiple VINs'

    move_id = fields.Many2one('account.move', required=True, readonly=True)
    dealer_id = fields.Many2one(
        'res.partner', string='Dealer/Customer', required=True,
        help="Defaults to the invoice's customer - change only if a "
             "different representative is collecting on their behalf.",
    )
    collection_date = fields.Date(
        required=True, default=lambda self: fields.Date.context_today(self),
    )
    collector_name = fields.Char(string="Collector's Name", required=True)
    collector_phone = fields.Char(string='Phone Number', required=True)
    x_is_dealer_collector = fields.Boolean(
        string='Dealer/Customer Collected',
        help="Tick this if the Dealer is picking up the documents "
             "themselves, rather than sending a representative. "
             "Collector's Name and Phone Number are then filled in from "
             "the Dealer's own profile and locked.",
    )
    id_document_type = fields.Many2one(
        'vehicle.id.document.type', string='ID Document Type',
    )
    id_document = fields.Binary(string='ID Document (Image or PDF)')
    id_document_filename = fields.Char()
    available_lot_ids = fields.Many2many(
        'stock.lot', compute='_compute_available_lot_ids',
        help="VINs on this invoice that are Ready for Collection and "
             "already have a VIN assigned. Units still needing a VIN "
             "assigned, or that are locked/already collected, don't "
             "show up here - handle those one at a time from the row's "
             "'Mark Collected' button instead.",
    )
    lot_ids = fields.Many2many(
        'stock.lot', string='VINs to Collect', required=True,
        domain="[('id', 'in', available_lot_ids)]",
    )
    x_collected_number = fields.Char(
        string='Number (How Much?)', compute='_compute_x_collected_number',
        help="How many documents this person is collecting in this "
             "batch - grows by 1 each time you add another VIN to the "
             "selection below. Every VIN in this batch is saved with "
             "this same total.",
    )

    @api.depends('move_id')
    def _compute_available_lot_ids(self):
        for wiz in self:
            if not wiz.move_id:
                wiz.available_lot_ids = False
                continue
            ready_units = wiz.move_id.unit_ids.filtered(
                lambda u: u.x_document_status == 'ready' and u.lot_id
            )
            wiz.available_lot_ids = ready_units.lot_id

    @api.onchange('x_is_dealer_collector', 'dealer_id')
    def _onchange_x_is_dealer_collector(self):
        for wiz in self:
            if wiz.x_is_dealer_collector and wiz.dealer_id:
                wiz.collector_name = wiz.dealer_id.name
                wiz.collector_phone = wiz.dealer_id.phone or wiz.dealer_id.mobile

    @api.depends('lot_ids')
    def _compute_x_collected_number(self):
        for wiz in self:
            wiz.x_collected_number = str(len(wiz.lot_ids)) if wiz.lot_ids else ''

    def action_confirm(self):
        self.ensure_one()
        if not self.lot_ids:
            raise UserError("Select at least one VIN to collect.")
        units = self.move_id.unit_ids.filtered(
            lambda u: u.lot_id in self.lot_ids and u.x_document_status == 'ready'
        ).sorted('sequence')
        if len(units) != len(self.lot_ids):
            raise UserError(
                "One or more selected VINs are no longer ready for "
                "collection (they may have just been collected, or "
                "locked by a payment change). Please close this window "
                "and reopen it."
            )
        collected_dt = datetime.combine(
            self.collection_date, fields.Datetime.now().time()
        )
        collected_number = str(len(units))
        for unit in units:
            collector_vals = {
                'x_document_collected_date': collected_dt,
                'x_collector_dealer_id': self.dealer_id.id,
                'x_collector_name': self.collector_name,
                'x_collected_number': collected_number,
                'x_collector_phone': self.collector_phone,
                'lot_id': unit.lot_id.id,
            }
            if self.id_document:
                collector_vals['x_id_document'] = self.id_document
                collector_vals['x_id_document_filename'] = self.id_document_filename
                collector_vals['x_id_document_type'] = self.id_document_type.id
            unit._apply_collection(collector_vals)
        return {'type': 'ir.actions.act_window_close'}
