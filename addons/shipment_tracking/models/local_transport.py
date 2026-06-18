# /custom_addons/shipment_tracking/models/local_transport.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class LocalTransportTrip(models.Model):
    """
    One record = one border-to-warehouse transport operation for a shipment.
    Created after the shipment reaches 'Arrived' at the border.
    """
    _name = 'local.transport.trip'
    _description = 'Local Container Transport Trip'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'reference'
    _order = 'departure_date desc, id desc'

    # ── Identity ──────────────────────────────────────────────────────────────
    reference = fields.Char(
        string='Trip Reference', required=True, copy=False,
        readonly=True, default=lambda self: _('New'), tracking=True,
    )

    # ── Linked Shipment ───────────────────────────────────────────────────────
    shipment_id = fields.Many2one(
        'shipment.tracking', string='Shipment', required=True, tracking=True,
        domain=[('state', '=', 'arrived')],
        help='Only shipments that have arrived at the border can be transported.',
    )

    # ── Read-only info from shipment ──────────────────────────────────────────
    supplier_id = fields.Many2one(
        related='shipment_id.supplier_id', string='Supplier', readonly=True, store=True,
    )
    port_of_discharge = fields.Char(
        related='shipment_id.port_of_discharge',
        string='Border / Port of Discharge', readonly=True,
    )
    shipment_actual_arrival = fields.Date(
        related='shipment_id.actual_arrival_date', string='Shipment Arrival Date', readonly=True,
    )

    # ── Route ─────────────────────────────────────────────────────────────────
    origin_location = fields.Char(
        string='Origin (Border)', required=True, tracking=True,
        placeholder='e.g. Djibouti Port',
    )
    destination_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Destination Warehouse',
        required=True,
        tracking=True,
        help='Select the warehouse where containers will be delivered.',
    )
    departure_date = fields.Date(string='Planned Departure Date', required=True, tracking=True)
    expected_arrival_date = fields.Date(string='Expected Warehouse Arrival', tracking=True)

    # ── Status ────────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',      'Draft'),
        ('dispatched', 'Dispatched'),
        ('in_transit', 'In Transit'),
        ('delivered',  'Delivered'),
        ('cancelled',  'Cancelled'),
    ], string='Trip Status', default='draft', required=True, tracking=True)

    # ── Truck Assignments (one line per truck) ────────────────────────────────
    assignment_ids = fields.One2many(
        'local.transport.assignment', 'trip_id', string='Truck Assignments',
    )
    assignment_count = fields.Integer(
        string='Trucks', compute='_compute_counts', store=True,
    )
    container_assignment_count = fields.Integer(
        string='Containers Assigned', compute='_compute_counts', store=True,
    )
    all_delivered = fields.Boolean(
        string='All Containers Delivered', compute='_compute_all_delivered', store=True,
    )

    notes = fields.Text(string='Internal Notes')

    # ── Computed ──────────────────────────────────────────────────────────────
    @api.depends('assignment_ids', 'assignment_ids.container2_id')
    def _compute_counts(self):
        for rec in self:
            rec.assignment_count = len(rec.assignment_ids)
            count = 0
            for a in rec.assignment_ids:
                count += 1
                if a.capacity == 'double' and a.container2_id:
                    count += 1
            rec.container_assignment_count = count

    @api.depends('assignment_ids.state')
    def _compute_all_delivered(self):
        for rec in self:
            assignments = rec.assignment_ids
            rec.all_delivered = bool(assignments) and all(
                a.state == 'delivered' for a in assignments
            )

    # ── Auto Reference ────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        shipment_ids = {vals['shipment_id'] for vals in vals_list if vals.get('shipment_id')}
        if shipment_ids:
            shipments = self.env['shipment.tracking'].browse(shipment_ids)
            for shipment in shipments:
                active_costs = shipment.cost_ids.filtered(lambda c: c.state != 'cancelled')
                if not active_costs:
                    raise UserError(_(
                        'No cost entries have been recorded for shipment "%s" yet.\n'
                        'Please add and pay all shipment costs before creating a local transport trip.'
                    ) % shipment.reference)
                unpaid_costs = active_costs.filtered(lambda c: c.state != 'paid')
                if unpaid_costs:
                    stage_names = ', '.join(unpaid_costs.mapped('stage_id.name'))
                    raise UserError(_(
                        'All costs for shipment "%s" must be marked as Paid before creating a '
                        'local transport trip.\nOutstanding cost stage(s): %s'
                    ) % (shipment.reference, stage_names))

        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'local.transport.trip'
                ) or _('New')
        return super().create(vals_list)

    # ── STAT BUTTON ACTIONS ───────────────────────────────────────────────────

    def action_view_trucks(self):
        """
        Opens the list of truck assignments (LocalTransportAssignment records)
        linked to this trip. Called by the '# Trucks' stat button.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Truck Assignments – %s') % self.reference,
            'res_model': 'local.transport.assignment',
            'view_mode': 'list,form',
            'domain': [('trip_id', '=', self.id)],
            'context': {
                'default_trip_id': self.id,
                # Pre-filter the container domain to this trip's shipment
                'default_shipment_id': self.shipment_id.id,
            },
        }

    def action_view_containers(self):
        """
        Opens the list of shipment.container records assigned to this trip
        (across all truck assignment slots). Called by the '# Containers' stat button.
        """
        self.ensure_one()
        # Collect all container IDs from both slots across every assignment
        container_ids = (
            self.assignment_ids.mapped('container_id').ids
            + self.assignment_ids.mapped('container2_id').ids
        )
        # Remove any False/0 values that come from empty slot 2
        container_ids = [cid for cid in container_ids if cid]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Containers – %s') % self.reference,
            'res_model': 'shipment.container',
            'view_mode': 'list,form',
            'domain': [('id', 'in', container_ids)],
            'context': {},
        }

    # ── Load containers from shipment ─────────────────────────────────────────
    def action_load_containers(self):
        """
        Auto-create one single-capacity truck line per container.
        Skips containers already assigned (checking both container slots).
        """
        self.ensure_one()
        if not self.shipment_id:
            raise UserError(_('Please select a shipment first.'))
        if self.shipment_id.state != 'arrived':
            raise UserError(_(
                'Shipment "%s" has not arrived yet.'
            ) % self.shipment_id.reference)

        already_assigned = (
            self.assignment_ids.mapped('container_id').ids
            + self.assignment_ids.mapped('container2_id').ids
        )
        new_lines = []
        for container in self.shipment_id.container_ids:
            if container.id not in already_assigned:
                new_lines.append({
                    'trip_id': self.id,
                    'container_id': container.id,
                    'capacity': 'single',
                })

        if not new_lines:
            raise UserError(_(
                'All containers from this shipment are already assigned, '
                'or the shipment has no containers.'
            ))

        self.env['local.transport.assignment'].create(new_lines)
        return True

    # ── Status transitions ────────────────────────────────────────────────────
    def action_dispatch(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft trips can be dispatched.'))
            if not rec.assignment_ids:
                raise UserError(_('Please add at least one truck assignment before dispatching.'))
            incomplete = rec.assignment_ids.filtered(
                lambda a: not a.driver_name or not a.truck_plate
            )
            if incomplete:
                raise UserError(_(
                    'The following truck lines are missing a driver or truck plate:\n%s'
                ) % '\n'.join(incomplete.mapped('truck_plate') or ['(unknown)']))
            rec.state = 'dispatched'

    def action_set_in_transit(self):
        for rec in self:
            if rec.state != 'dispatched':
                raise UserError(_('Only Dispatched trips can be set In Transit.'))
            rec.state = 'in_transit'
            rec.assignment_ids.filtered(lambda a: a.state == 'pending').write({'state': 'in_transit'})

    def action_mark_delivered(self):
        for rec in self:
            if rec.state not in ('dispatched', 'in_transit'):
                raise UserError(_('Trip must be Dispatched or In Transit to mark as Delivered.'))
            rec.state = 'delivered'
            rec.assignment_ids.filtered(lambda a: a.state != 'delivered').write({'state': 'delivered'})

    def action_cancel(self):
        for rec in self:
            if rec.state == 'delivered':
                raise UserError(_('Delivered trips cannot be cancelled.'))
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ('dispatched', 'cancelled'):
                raise UserError(_('Only Dispatched or Cancelled trips can be reset to Draft.'))
            rec.state = 'draft'


class LocalTransportAssignment(models.Model):
    """
    One line = ONE TRUCK with either 1 or 2 containers.
    - capacity='single' : truck carries container_id only
    - capacity='double' : truck carries container_id + container2_id
    """
    _name = 'local.transport.assignment'
    _description = 'Truck Container Assignment'
    _rec_name = 'truck_plate'
    _order = 'trip_id, id'

    # ── Parent Trip ───────────────────────────────────────────────────────────
    trip_id = fields.Many2one(
        'local.transport.trip', string='Trip', required=True, ondelete='cascade',
    )

    # ── Shipment (derived from trip) — used in container domain ──────────────
    shipment_id = fields.Many2one(
        related='trip_id.shipment_id',
        string='Shipment',
        store=True,
        readonly=True,
    )

    # ── Truck Capacity ────────────────────────────────────────────────────────
    capacity = fields.Selection([
        ('single', 'Single — carries 1 container'),
        ('double', 'Double — carries 2 containers'),
    ], string='Truck Capacity', required=True, default='single',
       help='Single-capacity trucks carry one container. '
            'Double-capacity trucks can carry two containers on a single trip.')

    # ── Container Slot 1 (always required) ───────────────────────────────────
    container_id = fields.Many2one(
        'shipment.container', string='Container 1', required=True,
        domain="[('shipment_id', '=', shipment_id)]",
    )
    container_number = fields.Char(
        related='container_id.container_number', string='Container 1 No.',
        readonly=True, store=True,
    )
    container_size = fields.Selection(
        related='container_id.size', string='Size 1', readonly=True,
    )
    seal_number = fields.Char(
        related='container_id.seal_number', string='Seal 1', readonly=True,
    )

    # ── Container Slot 2 (only when capacity='double') ────────────────────────
    container2_id = fields.Many2one(
        'shipment.container', string='Container 2',
        domain="[('shipment_id', '=', shipment_id)]",
        help='Only available for double-capacity trucks.',
    )
    container2_number = fields.Char(
        related='container2_id.container_number', string='Container 2 No.',
        readonly=True, store=True,
    )
    container2_size = fields.Selection(
        related='container2_id.size', string='Size 2', readonly=True,
    )
    seal2_number = fields.Char(
        related='container2_id.seal_number', string='Seal 2', readonly=True,
    )

    # ── Truck & Driver ────────────────────────────────────────────────────────
    truck_plate = fields.Char(
        string='Truck Plate No.', required=True,
        help='Vehicle license plate number',
    )
    driver_name = fields.Char(string='Driver Name', required=True)
    driver_phone = fields.Char(string='Driver Phone')
    driver_license = fields.Char(string='Driver License No.')

    # ── Per-truck delivery status ─────────────────────────────────────────────
    state = fields.Selection([
        ('pending',    'Pending'),
        ('in_transit', 'In Transit'),
        ('delivered',  'Delivered'),
    ], string='Status', default='pending', required=True, tracking=True)

    actual_delivery_date = fields.Date(string='Actual Delivery Date')
    notes = fields.Char(string='Notes')

    # ── Constraints ───────────────────────────────────────────────────────────
    @api.constrains('capacity', 'container2_id')
    def _check_double_capacity_slot(self):
        for rec in self:
            if rec.capacity == 'single' and rec.container2_id:
                raise ValidationError(_(
                    'Truck "%s" is set as Single capacity but has a second container assigned. '
                    'Change capacity to Double or remove Container 2.'
                ) % rec.truck_plate)

    @api.constrains('container_id', 'container2_id')
    def _check_no_same_container_in_both_slots(self):
        for rec in self:
            if rec.container_id and rec.container2_id and rec.container_id == rec.container2_id:
                raise ValidationError(_(
                    'Container 1 and Container 2 cannot be the same container ("%s").'
                ) % rec.container_id.container_number)

    @api.constrains('container_id', 'container2_id', 'trip_id')
    def _check_containers_belong_to_shipment(self):
        for rec in self:
            shipment = rec.trip_id.shipment_id
            for c in [rec.container_id, rec.container2_id]:
                if c and c.shipment_id != shipment:
                    raise ValidationError(_(
                        'Container "%s" does not belong to shipment "%s".'
                    ) % (c.container_number, shipment.reference))

    @api.constrains('container_id', 'container2_id', 'trip_id')
    def _check_no_duplicate_container_in_trip(self):
        """Ensure no container is assigned to more than one truck in the same trip."""
        for rec in self:
            for _slot, c in [('container_id', rec.container_id), ('container2_id', rec.container2_id)]:
                if not c:
                    continue
                dup1 = self.search([
                    ('trip_id', '=', rec.trip_id.id),
                    ('container_id', '=', c.id),
                    ('id', '!=', rec.id),
                ])
                dup2 = self.search([
                    ('trip_id', '=', rec.trip_id.id),
                    ('container2_id', '=', c.id),
                    ('id', '!=', rec.id),
                ])
                if dup1 or dup2:
                    raise ValidationError(_(
                        'Container "%s" is already assigned to another truck in this trip.'
                    ) % c.container_number)

    # ── onchange: clear container2 if switching back to single ────────────────
    @api.onchange('capacity')
    def _onchange_capacity(self):
        if self.capacity == 'single':
            self.container2_id = False

    # ── Per-truck delivery ────────────────────────────────────────────────────
    def action_mark_delivered(self):
        for rec in self:
            rec.write({
                'state': 'delivered',
                'actual_delivery_date': rec.actual_delivery_date or fields.Date.today(),
            })
