# /custom_addons/shipment_tracking/models/shipment.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ShipmentTracking(models.Model):
    _name = 'shipment.tracking'
    _description = 'Import Shipment Tracking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'reference'
    _order = 'eta asc, id desc'

    reference = fields.Char(
        string='Shipment Reference', required=True, copy=False,
        readonly=True, default=lambda self: _('New'), tracking=True,
    )
    carrier = fields.Char(string='Carrier / Shipping Line', required=True, tracking=True)
    incoterm_id = fields.Many2one('account.incoterms', string='Incoterms', tracking=True)
    port_of_loading = fields.Char(string='Port of Loading', tracking=True)
    port_of_discharge = fields.Char(string='Port of Discharge', tracking=True)

    # FIX #2: both dates required
    etd = fields.Date(string='ETD (Est. Departure)', required=True, tracking=True)
    eta = fields.Date(string='ETA (Est. Arrival)', required=True, tracking=True)
    actual_arrival_date = fields.Date(string='Actual Arrival Date', tracking=True)

    purchase_order_id = fields.Many2one(
        'purchase.order', string='Purchase Order', tracking=True,
        domain=[('state', 'in', ['purchase', 'done'])],
    )
    supplier_id = fields.Many2one(
        related='purchase_order_id.partner_id', string='Supplier', store=True, readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='purchase_order_id.currency_id', readonly=True, store=True,
    )
    po_amount_total = fields.Monetary(
        related='purchase_order_id.amount_total', string='PO Total',
        currency_field='currency_id', readonly=True, store=True,
    )

    # FIX #1: Cleared removed — Arrived is the final state
    state = fields.Selection([
        ('planned',    'Planned'),
        ('in_transit', 'In Transit'),
        ('arrived',    'Arrived'),
    ], string='Status', default='planned', required=True, tracking=True)

    container_ids = fields.One2many('shipment.container', 'shipment_id', string='Containers')
    container_count = fields.Integer(
        string='Number of Containers', compute='_compute_container_count', store=True,
    )
    transport_trip_ids = fields.One2many(
        'local.transport.trip', 'shipment_id', string='Local Transport Trips',
    )
    transport_trip_count = fields.Integer(
        string='Transport Trips', compute='_compute_transport_trip_count', store=True,
    )
    notes = fields.Text(string='Internal Notes')
    active = fields.Boolean(default=True)

    @api.depends('container_ids')
    def _compute_container_count(self):
        for rec in self:
            rec.container_count = len(rec.container_ids)

    @api.depends('transport_trip_ids')
    def _compute_transport_trip_count(self):
        for rec in self:
            rec.transport_trip_count = len(rec.transport_trip_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('shipment.tracking') or _('New')
        return super().create(vals_list)

    def action_view_containers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Containers'),
            'res_model': 'shipment.container', 'view_mode': 'list,form',
            'domain': [('shipment_id', '=', self.id)],
            'context': {'default_shipment_id': self.id},
        }

    def action_view_transport_trips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Local Transport Trips'),
            'res_model': 'local.transport.trip', 'view_mode': 'list,form',
            'domain': [('shipment_id', '=', self.id)],
            'context': {'default_shipment_id': self.id},
        }

    def action_create_transport_trip(self):
        self.ensure_one()
        if self.state != 'arrived':
            raise UserError(_('Local transport trips can only be created for Arrived shipments.'))
        return {
            'type': 'ir.actions.act_window', 'name': _('New Transport Trip'),
            'res_model': 'local.transport.trip', 'view_mode': 'form',
            'context': {
                'default_shipment_id': self.id,
                'default_origin_location': self.port_of_discharge or '',
            },
        }

    def action_set_in_transit(self):
        for rec in self:
            if rec.state != 'planned':
                raise UserError(_('Only Planned shipments can be set to In Transit.'))
            if not rec.container_ids:
                raise UserError(_('Please add at least one container before departing.'))
            rec.state = 'in_transit'

    def action_set_arrived(self):
        for rec in self:
            if rec.state != 'in_transit':
                raise UserError(_('Only In Transit shipments can be set to Arrived.'))
            rec.write({
                'state': 'arrived',
                'actual_arrival_date': rec.actual_arrival_date or fields.Date.today(),
            })

    # FIX #1: action_set_cleared removed. Reset only allowed from in_transit.
    def action_reset_to_planned(self):
        for rec in self:
            if rec.state != 'in_transit':
                raise UserError(_('Only In Transit shipments can be reset to Planned.'))
            rec.state = 'planned'
