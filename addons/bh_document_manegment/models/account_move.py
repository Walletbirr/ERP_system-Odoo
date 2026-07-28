from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_date_fully_paid = fields.Date(
        string='Date Fully Paid', copy=False, readonly=True,
        help="Automatically stamped the first time this invoice's payment "
             "status becomes Paid / In Payment.",
    )
    unit_ids = fields.One2many(
        'vehicle.document.unit', 'move_id', string='Vehicle Units',
    )
    x_has_vehicle_units = fields.Boolean(
        compute='_compute_x_has_vehicle_units', store=True,
    )
    x_units_summary_move = fields.Char(
        string='Document Status', compute='_compute_x_units_summary_move',
    )

    @api.depends('unit_ids')
    def _compute_x_has_vehicle_units(self):
        for move in self:
            move.x_has_vehicle_units = bool(move.unit_ids)

    @api.depends('unit_ids.x_document_status')
    def _compute_x_units_summary_move(self):
        for move in self:
            units = move.unit_ids
            if not units:
                move.x_units_summary_move = ''
                continue
            total = len(units)
            collected = len(units.filtered(lambda u: u.x_document_status == 'collected'))
            ready = len(units.filtered(lambda u: u.x_document_status == 'ready'))
            locked = total - collected - ready
            move.x_units_summary_move = "%d/%d collected · %d ready · %d locked" % (
                collected, total, ready, locked
            )

    def _compute_payment_state(self):
        # NOTE: overrides a core Odoo compute method
        # (account.move.payment_state, compute='_compute_payment_state').
        # Verified against Odoo 18 core source. If a future point release
        # renames it, this override simply stops firing (safe failure:
        # x_date_fully_paid just won't get stamped) - it will not break
        # invoicing itself.
        super()._compute_payment_state()
        today = fields.Date.context_today(self)
        for move in self:
            if move.payment_state in ('paid', 'in_payment') and not move.x_date_fully_paid:
                move.x_date_fully_paid = today

    def action_post(self):
        res = super().action_post()
        self.invoice_line_ids._generate_vehicle_document_units()
        return res

    def action_open_multi_collection_wizard(self):
        self.ensure_one()
        ready_units = self.unit_ids.filtered(
            lambda u: u.x_document_status == 'ready' and u.lot_id
        )
        if not ready_units:
            raise UserError(
                "There are no units on this invoice that are both Ready "
                "for Collection and already have a VIN assigned. Units "
                "still needing a VIN must be assigned one first (row's "
                "VIN cell, or 'Mark Collected' for a single unit)."
            )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Collect Multiple Documents',
            'res_model': 'vehicle.document.multi.collection.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'bh_document_manegment.view_vehicle_document_multi_collection_wizard_form'
            ).id,
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_dealer_id': self.partner_id.id,
            },
        }


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    x_is_vehicle_line = fields.Boolean(
        string='Requires Document Tracking',
        compute='_compute_x_is_vehicle_line', store=True,
    )
    x_move_date_fully_paid = fields.Date(
        string='Fully Paid On',
        related='move_id.x_date_fully_paid', store=True, readonly=True,
    )
    unit_ids = fields.One2many(
        'vehicle.document.unit', 'move_line_id', string='Vehicle Units',
    )
    x_units_summary = fields.Char(
        string='Document Status', compute='_compute_x_units_summary',
    )
    x_has_unassigned_units = fields.Boolean(
        compute='_compute_x_has_unassigned_units',
    )

    @api.depends('product_id.categ_id.x_effective_document_tracking')
    def _compute_x_is_vehicle_line(self):
        for line in self:
            line.x_is_vehicle_line = bool(
                line.product_id.categ_id.x_effective_document_tracking
            )

    @api.depends('unit_ids.x_document_status')
    def _compute_x_units_summary(self):
        for line in self:
            if not line.x_is_vehicle_line:
                line.x_units_summary = ''
                continue
            if not line.unit_ids:
                line.x_units_summary = 'Not generated yet'
                continue
            total = len(line.unit_ids)
            collected = len(line.unit_ids.filtered(
                lambda u: u.x_document_status == 'collected'
            ))
            ready = len(line.unit_ids.filtered(
                lambda u: u.x_document_status == 'ready'
            ))
            line.x_units_summary = "%d/%d collected (%d ready)" % (
                collected, total, ready
            )

    @api.depends('unit_ids.lot_id')
    def _compute_x_has_unassigned_units(self):
        for line in self:
            line.x_has_unassigned_units = bool(
                line.unit_ids.filtered(lambda u: not u.lot_id)
            )

    def _get_delivered_lots(self):
        """Ordered stock.move.line records - the actual delivery history
        for this invoice line's product - coming from the 'Done' outgoing
        transfer(s) of the sale order(s) behind this invoice line. This is
        the source of truth for which physical VIN/Serial left the
        warehouse for this line, instead of letting a user pick any lot
        of the product still sitting in the lot registry.
        """
        self.ensure_one()
        moves = self.sale_line_ids.move_ids.filtered(
            lambda m: m.state == 'done'
            and m.picking_type_id.code == 'outgoing'
            and m.product_id == self.product_id
        )
        move_lines = moves.move_line_ids.filtered(lambda ml: ml.lot_id)
        return move_lines.sorted(
            key=lambda ml: (ml.picking_id.date_done or ml.date, ml.id)
        )

    def _generate_vehicle_document_units(self):
        """Create one vehicle.document.unit per physical unit on qualifying
        lines. Idempotent - safe to call repeatedly (e.g. via the manual
        'Generate Units' button for invoices posted before this module was
        installed): lines that already have units are skipped.

        Each created unit is auto-matched, in order, to a Lot/Serial that
        was actually delivered for this line's sale order (see
        _get_delivered_lots). Units that can't be matched yet (e.g. the
        delivery hasn't been validated when the invoice is posted) are
        left without a Lot/Serial - these get backfilled automatically
        the moment the outgoing delivery is later validated (see
        stock_move.py: StockMove._sync_vehicle_document_units_after_delivery),
        so 'Sync VINs from Delivery' / action_sync_units_button only
        needs to be clicked by hand as a fallback (e.g. deliveries
        validated before this module was installed, or re-triggering
        after a manual data fix).
        """
        Unit = self.env['vehicle.document.unit'].sudo()
        for line in self:
            if not line.x_is_vehicle_line or line.unit_ids:
                continue
            qty = int(line.quantity)
            if qty <= 0:
                continue
            unit_value = round(line.price_total / line.quantity, 2) if line.quantity else 0.0
            free_lots = line._get_free_delivered_lots()
            for seq in range(1, qty + 1):
                vals = {
                    'move_line_id': line.id,
                    'sequence': seq,
                    'unit_price': unit_value,
                }
                if free_lots:
                    vals['lot_id'] = free_lots.pop(0).id
                Unit.create(vals)

    def _get_free_delivered_lots(self):
        """Delivered lots for this line's product (see _get_delivered_lots)
        that are not already assigned to some other vehicle.document.unit
        anywhere in the system. Returned as a plain ordered list of
        stock.lot records, ready to be consumed one-by-one.
        """
        self.ensure_one()
        delivered_lots = self._get_delivered_lots().lot_id
        if not delivered_lots:
            return []
        already_used = self.env['vehicle.document.unit'].sudo().search([
            ('lot_id', 'in', delivered_lots.ids),
        ]).mapped('lot_id')
        return [lot for lot in delivered_lots if lot not in already_used]

    def action_sync_units_button(self):
        """Backfill lot_id on any of this line's units that don't have one
        yet, using whatever has been delivered since the units were first
        generated (typical case: invoice posted, and thus units created,
        before the delivery was validated).
        """
        self.ensure_one()
        unassigned = self.unit_ids.filtered(lambda u: not u.lot_id).sorted('sequence')
        if not unassigned:
            return
        free_lots = self._get_free_delivered_lots()
        for unit in unassigned:
            if not free_lots:
                break
            unit.lot_id = free_lots.pop(0).id

    def action_generate_units_button(self):
        self.ensure_one()
        if self.move_id.state != 'posted':
            raise UserError(
                "The invoice must be posted before generating vehicle units."
            )
        self._generate_vehicle_document_units()

    def action_view_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vehicle Units - %s' % (self.product_id.display_name or ''),
            'res_model': 'vehicle.document.unit',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('bh_document_manegment.view_vehicle_document_tracking_list').id, 'list'),
                (self.env.ref('bh_document_manegment.view_vehicle_document_tracking_form').id, 'form'),
            ],
            'domain': [('move_line_id', '=', self.id)],
        }
