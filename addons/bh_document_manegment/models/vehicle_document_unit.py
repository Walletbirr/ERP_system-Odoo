from odoo import api, fields, models
from odoo.exceptions import UserError


class VehicleDocumentUnit(models.Model):
    _name = 'vehicle.document.unit'
    _description = 'Vehicle Document Release - Per Unit Tracking'
    _order = 'move_id, sequence, id'

    move_line_id = fields.Many2one(
        'account.move.line', required=True, ondelete='cascade', index=True,
    )
    move_id = fields.Many2one(
        'account.move', related='move_line_id.move_id', store=True,
        index=True, string='Invoice',
    )
    partner_id = fields.Many2one(
        'res.partner', related='move_id.partner_id', store=True,
        string='Customer',
    )
    product_id = fields.Many2one(
        'product.product', related='move_line_id.product_id', store=True,
    )
    x_move_date_fully_paid = fields.Date(
        related='move_id.x_date_fully_paid', store=True,
        string='Invoice Fully Paid On',
    )
    sequence = fields.Integer(default=1, string='Unit #')
    x_row_number = fields.Integer(
        string='No.', compute='_compute_x_row_number',
        help="Plain running count of this invoice's units (1, 2, 3...), "
             "regardless of which product line they belong to - unlike "
             "'Unit #', which restarts at 1 for each product.",
    )
    lot_id = fields.Many2one(
        'stock.lot', string='VIN',
        domain="[('product_id', '=', product_id)]",
        help="The specific vehicle (by VIN) this row refers to. Normally "
             "auto-matched from the actual delivery of the sale order "
             "behind this invoice line (see 'Sync VINs from Delivery'); "
             "only needs to be picked by hand if that match can't be made "
             "(e.g. delivery not validated yet).",
    )
    x_lot_secondary_number = fields.Char(
        related='lot_id.x_secondary_number', string='Serial Number',
    )
    shipment_reference = fields.Char(
        related='lot_id.shipment_reference', string='Shipment',
    )
    unit_price = fields.Float(
        string='Unit Value',
        help="This unit's share of the invoice total (incl. tax), fixed "
             "at the moment the invoice was posted.",
    )
    x_document_collected = fields.Boolean(
        string='Document Collected', copy=False, readonly=True,
    )
    x_document_collected_date = fields.Datetime(
        string='Collected On', copy=False, readonly=True,
    )
    x_document_collected_by = fields.Many2one(
        'res.users', string='Collected By', copy=False, readonly=True,
    )
    x_document_notes = fields.Char(string='Collection Notes', copy=False)
    x_collector_dealer_id = fields.Many2one(
        'res.partner', string='Dealer (at Collection)', copy=False,
        help="Usually the same as Customer, but editable in case a "
             "different company representative is confirmed at pickup.",
    )
    x_collector_name = fields.Char(
        string="Collector's Name", copy=False,
        help="Name of the person who physically came to collect the document.",
    )
    x_collected_number = fields.Char(
        string='Number (How Much?)', copy=False,
        help="How many documents the person collected or received.",
    )
    x_collector_phone = fields.Char(string='Collector Phone', copy=False)
    x_id_document_type = fields.Many2one(
        'vehicle.id.document.type', string='ID Document Type', copy=False,
    )
    x_id_document = fields.Binary(
        string='ID Document', copy=False, attachment=True,
        help="Scan or photo of the collector's ID (image or PDF).",
    )
    x_id_document_filename = fields.Char(copy=False)
    x_document_status = fields.Selection([
        ('na', 'Not Applicable'),
        ('locked', 'Locked - Payment Pending'),
        ('ready', 'Ready for Collection'),
        ('collected', 'Collected'),
    ], string='Document Status', compute='_compute_x_document_status',
        store=True,
    )
    x_can_manage_documents = fields.Boolean(
        compute='_compute_x_can_manage_documents',
        help="Technical field - whether the current user is in the "
             "'Document Collector' group and may act on document "
             "collection (assign a VIN, mark collected, etc.), as "
             "opposed to only viewing status read-only.",
    )

    def _compute_x_can_manage_documents(self):
        can_manage = self.env.user.has_group(
            'bh_document_manegment.group_document_collector'
        )
        for unit in self:
            unit.x_can_manage_documents = can_manage

    @api.depends(
        'x_document_collected',
        'move_line_id.x_is_vehicle_line',
        'move_id.payment_state', 'move_id.amount_total', 'move_id.amount_residual',
        'move_id.unit_ids.x_document_collected', 'move_id.unit_ids.unit_price',
    )
    def _compute_x_document_status(self):
        for unit in self:
            if not unit.move_line_id.x_is_vehicle_line:
                unit.x_document_status = 'na'
                continue
            if unit.x_document_collected:
                unit.x_document_status = 'collected'
                continue
            headroom = unit._get_payment_headroom()
            unit.x_document_status = (
                'ready' if headroom >= (unit.unit_price - 0.01) else 'locked'
            )

    @api.depends('move_id.unit_ids')
    def _compute_x_row_number(self):
        seen_moves = self.env['account.move']
        for unit in self:
            move = unit.move_id
            if move in seen_moves:
                continue
            seen_moves |= move
            for idx, u in enumerate(move.unit_ids, start=1):
                u.x_row_number = idx

    def _get_payment_headroom(self):
        """How much of this invoice's paid amount is still unallocated to
        an already-released document, i.e. available to unlock more units.
        """
        self.ensure_one()
        move = self.move_id
        paid_amount = move.amount_total - move.amount_residual
        allocated = sum(
            u.unit_price for u in move.unit_ids if u.x_document_collected
        )
        return paid_amount - allocated

    def action_open_collection_wizard(self):
        self.ensure_one()
        if self.x_document_status == 'collected':
            raise UserError("This document has already been marked as collected.")
        if self.x_document_status != 'ready':
            headroom = self._get_payment_headroom()
            shortfall = self.unit_price - headroom
            raise UserError(
                "Cannot release the document for Unit #%s of '%s' "
                "(Invoice %s).\n\n"
                "This unit is valued at %.2f, but only %.2f of the paid "
                "amount on this invoice is currently unallocated to a "
                "released document. The client needs to pay at least "
                "%.2f more before this specific unit's document can be "
                "released." % (
                    self.sequence, self.product_id.display_name,
                    self.move_id.name, self.unit_price, headroom, shortfall,
                )
            )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirm Document Collection',
            'res_model': 'vehicle.document.collection.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'bh_document_manegment.view_vehicle_document_collection_wizard_form'
            ).id,
            'target': 'new',
            'context': {
                'default_unit_id': self.id,
                'default_dealer_id': self.partner_id.id,
                'default_lot_id': self.lot_id.id,
            },
        }

    def _apply_collection(self, collector_vals):
        """Called by the wizard once its form is confirmed. Kept separate
        from action_mark_document_collected so both the simple path (no
        collector details) and the wizard path share the same guard logic
        via action_open_collection_wizard's pre-check.
        """
        self.ensure_one()
        vals = {
            'x_document_collected': True,
            'x_document_collected_date': fields.Datetime.now(),
            'x_document_collected_by': self.env.user.id,
        }
        vals.update(collector_vals)
        self.write(vals)

    def action_mark_document_collected(self):
        for unit in self:
            if unit.x_document_status == 'collected':
                continue
            if unit.x_document_status != 'ready':
                headroom = unit._get_payment_headroom()
                shortfall = unit.unit_price - headroom
                raise UserError(
                    "Cannot release the document for Unit #%s of '%s' "
                    "(Invoice %s).\n\n"
                    "This unit is valued at %.2f, but only %.2f of the "
                    "paid amount on this invoice is currently unallocated "
                    "to a released document. The client needs to pay at "
                    "least %.2f more before this specific unit's document "
                    "can be released." % (
                        unit.sequence, unit.product_id.display_name,
                        unit.move_id.name, unit.unit_price, headroom,
                        shortfall,
                    )
                )
            unit.write({
                'x_document_collected': True,
                'x_document_collected_date': fields.Datetime.now(),
                'x_document_collected_by': self.env.user.id,
            })

    def action_view_collector_details(self):
        self.ensure_one()
        if self.x_document_status != 'collected':
            raise UserError("This document hasn't been collected yet - nothing to show.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Collector Details - %s' % (self.product_id.display_name or ''),
            'res_model': 'vehicle.document.unit',
            'view_mode': 'form',
            'views': [
                (self.env.ref('bh_document_manegment.view_vehicle_document_tracking_form').id, 'form'),
            ],
            'res_id': self.id,
            'target': 'new',
        }

    def action_undo_document_collected(self):
        for unit in self:
            unit.write({
                'x_document_collected': False,
                'x_document_collected_date': False,
                'x_document_collected_by': False,
            })