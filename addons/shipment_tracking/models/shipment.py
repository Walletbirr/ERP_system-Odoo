# /custom_addons/shipment_tracking/models/shipment.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ShipmentTracking(models.Model):
    _name = 'shipment.tracking'
    _description = 'Import Shipment Tracking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'reference'
    _order = 'eta asc, id desc'

    # ── Identity ─────────────────────────────────────────────────────────────
    reference = fields.Char(
        string='Shipment Reference', required=True, copy=False,
        readonly=True, default=lambda self: _('New'), tracking=True,
    )
    carrier = fields.Char(string='Carrier / Shipping Line', required=True, tracking=True)
    incoterm_id = fields.Many2one('account.incoterms', string='Incoterms', tracking=True)
    port_of_loading = fields.Char(string='Port of Loading', tracking=True)
    port_of_discharge = fields.Char(string='Port of Discharge', tracking=True)
    etd = fields.Date(string='ETD (Est. Departure)', required=True, tracking=True)
    eta = fields.Date(string='ETA (Est. Arrival)', required=True, tracking=True)
    actual_arrival_date = fields.Date(string='Actual Arrival Date', tracking=True)

    # ── Intermediate Ports ────────────────────────────────────────────────────
    intermediate_port_ids = fields.One2many(
        'shipment.port', 'shipment_id',
        string='Intermediate Ports',
    )

    # ── Purchase Order ────────────────────────────────────────────────────────
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

    # ── Status ────────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('planned',    'Planned'),
        ('in_transit', 'In Transit'),
        ('arrived',    'Arrived'),
    ], string='Status', default='planned', required=True, tracking=True)

    current_port_label = fields.Char(
        string='Current Port', compute='_compute_current_port_label', store=False,
    )

    # Dynamic button labels — used directly in the view via attrs/label
    arrive_button_label = fields.Char(
        string='Arrive Button Label', compute='_compute_dynamic_labels', store=False,
    )
    depart_button_label = fields.Char(
        string='Depart Button Label', compute='_compute_dynamic_labels', store=False,
    )
    # Dynamic "Depart to <destination>" label for the final in-transit button
    at_port_button_label = fields.Char(
        string='At Port Button Label', compute='_compute_dynamic_labels', store=False,
    )
    # Visibility flags — only one button group is shown at a time
    show_arrive_btn = fields.Boolean(compute='_compute_dynamic_labels', store=False)
    show_depart_btn = fields.Boolean(compute='_compute_dynamic_labels', store=False)
    show_final_btn  = fields.Boolean(compute='_compute_dynamic_labels', store=False)
    # True once any intermediate port has been reached or passed (hides Reset button)
    has_started_moving = fields.Boolean(
        string='Has Started Moving', compute='_compute_has_started_moving', store=False,
    )
    # Used to build a dynamic statusbar (stored as JSON-like string for the widget)
    port_progress_summary = fields.Char(
        string='Port Progress', compute='_compute_port_progress_summary', store=False,
    )
    # HTML progress bar rendered in the form view header area
    progress_bar_html = fields.Html(
        string='Progress Bar', compute='_compute_progress_bar_html',
        store=False, sanitize=False,
    )

    # ── Containers ────────────────────────────────────────────────────────────
    container_ids = fields.One2many('shipment.container', 'shipment_id', string='Containers')
    container_count = fields.Integer(compute='_compute_container_count', store=True, string='Containers')
    transport_trip_ids = fields.One2many('local.transport.trip', 'shipment_id', string='Transport Trips')
    transport_trip_count = fields.Integer(compute='_compute_transport_trip_count', store=True, string='Transport Trips')

    # ── Costs ─────────────────────────────────────────────────────────────────
    cost_ids = fields.One2many('shipment.cost', 'shipment_id', string='Cost Stages')
    cost_count = fields.Integer(compute='_compute_cost_count', store=True, string='Cost Entries')

    # ── Cost Summary ──────────────────────────────────────────────────────────
    cost_currency_id = fields.Many2one(
        'res.currency', string='Cost Currency',
        default=lambda self: self.env.company.currency_id,
    )
    total_cost = fields.Monetary(
        string='Total Shipment Cost', compute='_compute_cost_summary',
        store=True, currency_field='cost_currency_id',
    )
    total_paid = fields.Monetary(
        string='Total Paid', compute='_compute_cost_summary',
        store=True, currency_field='cost_currency_id',
    )
    total_pending = fields.Monetary(
        string='Total Pending', compute='_compute_cost_summary',
        store=True, currency_field='cost_currency_id',
    )
    has_overdue_payments = fields.Boolean(compute='_compute_cost_summary', store=True)

    # ── Payment Confirmation ──────────────────────────────────────────────────
    payment_confirmed = fields.Boolean(string='Payment Confirmed', default=False, tracking=True)
    payment_confirmed_date = fields.Date(string='Payment Confirmed On', tracking=True)
    payment_confirmed_by = fields.Many2one('res.users', string='Confirmed By', tracking=True)

    # ── Insurance ─────────────────────────────────────────────────────────────
    has_insurance = fields.Boolean(string='Insured', default=False, tracking=True)
    insurance_reference = fields.Char(string='Insurance Policy No.', tracking=True)

    notes = fields.Text(string='Internal Notes')
    active = fields.Boolean(default=True)

    # ── Computed ──────────────────────────────────────────────────────────────
    @api.constrains('etd', 'eta')
    def _check_dates_not_in_past(self):
        today = fields.Date.today()
        for rec in self:
            if rec.etd and rec.etd < today:
                raise ValidationError(_(
                    'ETD (Est. Departure) cannot be set to a past date. '
                    'Please select today or a future date.'
                ))
            if rec.eta and rec.eta < today:
                raise ValidationError(_(
                    'ETA (Est. Arrival) cannot be set to a past date. '
                    'Please select today or a future date.'
                ))
            if rec.etd and rec.eta and rec.etd == rec.eta:
                raise ValidationError(_(
                    'ETD (Est. Departure) and ETA (Est. Arrival) cannot be the same date. '
                    'Arrival must be after departure.'
                ))
            if rec.etd and rec.eta and rec.eta < rec.etd:
                raise ValidationError(_(
                    'ETA (Est. Arrival) cannot be earlier than ETD (Est. Departure).'
                ))

    @api.depends('container_ids')
    def _compute_container_count(self):
        for rec in self:
            rec.container_count = len(rec.container_ids)

    @api.depends('transport_trip_ids')
    def _compute_transport_trip_count(self):
        for rec in self:
            rec.transport_trip_count = len(rec.transport_trip_ids)

    @api.depends('cost_ids', 'cost_ids.state')
    def _compute_cost_count(self):
        for rec in self:
            rec.cost_count = len(rec.cost_ids.filtered(lambda c: c.state != 'cancelled'))

    @api.depends('cost_ids', 'cost_ids.state', 'cost_ids.amount_company', 'cost_ids.due_date')
    def _compute_cost_summary(self):
        today = fields.Date.today()
        for rec in self:
            active = rec.cost_ids.filtered(lambda c: c.state != 'cancelled')
            total = paid = pending = 0.0
            overdue = False
            for c in active:
                total += c.amount_company
                if c.state == 'paid':
                    paid += c.amount_company
                else:
                    pending += c.amount_company
                if c.state == 'pending' and c.due_date and c.due_date < today:
                    overdue = True
            rec.total_cost = total
            rec.total_paid = paid
            rec.total_pending = pending
            rec.has_overdue_payments = overdue
            rec.cost_currency_id = self.env.company.currency_id

    @api.depends('state', 'intermediate_port_ids', 'intermediate_port_ids.state',
                 'intermediate_port_ids.name', 'port_of_discharge')
    def _compute_dynamic_labels(self):
        """
        Only ONE button group is visible at a time:

        Phase A — pending port exists, none reached yet:
            → "Arrive at [next port]"

        Phase B — a port is currently reached (ship docked):
            → "Depart from [current port]"

        Phase C — all intermediate ports passed (or none exist):
            → "Depart to [destination]"
        """
        for rec in self:
            discharge = rec.port_of_discharge or 'Destination Port'

            reached_port = rec.intermediate_port_ids.filtered(
                lambda p: p.state == 'reached'
            )[:1]
            pending_port = rec.intermediate_port_ids.filtered(
                lambda p: p.state == 'pending'
            )[:1]
            all_passed = rec._all_intermediate_ports_passed()

            # Phase A: heading toward next intermediate port
            if pending_port and not reached_port:
                rec.arrive_button_label  = 'Arrive at %s' % pending_port.name
                rec.depart_button_label  = ''
                rec.at_port_button_label = ''
                rec.show_arrive_btn      = True
                rec.show_depart_btn      = False
                rec.show_final_btn       = False

            # Phase B: docked at an intermediate port
            elif reached_port:
                rec.arrive_button_label  = ''
                rec.depart_button_label  = 'Depart from %s' % reached_port.name
                rec.at_port_button_label = ''
                rec.show_arrive_btn      = False
                rec.show_depart_btn      = True
                rec.show_final_btn       = False

            # Phase C: all stops cleared — ready for final leg to destination
            else:
                rec.arrive_button_label  = ''
                rec.depart_button_label  = ''
                rec.at_port_button_label = 'Arrived at %s' % discharge
                rec.show_arrive_btn      = False
                rec.show_depart_btn      = False
                rec.show_final_btn       = True

    @api.depends('state', 'port_of_loading', 'port_of_discharge')
    def _compute_progress_bar_html(self):
        """Build a clean HTML progress bar showing all shipment stages."""
        for rec in self:
            destination = rec.port_of_discharge or 'Destination Port'
            state_order = ['planned', 'in_transit', 'arrived']
            current_idx = state_order.index(rec.state) if rec.state in state_order else 0

            steps = [
                ('planned',    'Planned',    '1'),
                ('in_transit', 'In Transit', '2'),
                ('arrived',    destination,  '3'),
            ]

            html_steps = ''
            for idx, (key, label, icon) in enumerate(steps):
                step_idx = state_order.index(key)
                if step_idx < current_idx:
                    css = 'done'
                    circle_icon = '✓'
                elif step_idx == current_idx:
                    css = 'active'
                    circle_icon = icon
                else:
                    css = 'pending'
                    circle_icon = icon

                sublabel = (
                    '<div class="shp_sublabel">Current</div>'
                    if css == 'active' else ''
                )

                html_steps += (
                    '<div class="shp_step {css}">'
                    '<div class="shp_circle">{icon}</div>'
                    '<div class="shp_label">{label}{sub}</div>'
                    '</div>'
                ).format(css=css, icon=circle_icon, label=label, sub=sublabel)

            rec.progress_bar_html = (
                '<div class="shp_progress_bar">%s</div>' % html_steps
            )

    @api.depends('state', 'intermediate_port_ids', 'intermediate_port_ids.state',
                 'intermediate_port_ids.name', 'port_of_loading', 'port_of_discharge')
    def _compute_port_progress_summary(self):
        """Builds a readable progress string: Loading → [ports] → Discharge"""
        for rec in self:
            parts = [rec.port_of_loading or 'Origin']
            for p in rec.intermediate_port_ids:
                if p.state == 'passed':
                    parts.append('✓ %s' % p.name)
                elif p.state == 'reached':
                    parts.append('⬤ %s' % p.name)
                else:
                    parts.append('○ %s' % p.name)
            parts.append(rec.port_of_discharge or 'Destination')
            rec.port_progress_summary = ' → '.join(parts)

    @api.depends('state', 'intermediate_port_ids', 'intermediate_port_ids.state',
                 'intermediate_port_ids.name')
    def _compute_current_port_label(self):
        for rec in self:
            if rec.state == 'planned':
                rec.current_port_label = rec.port_of_loading or 'Origin'
            elif rec.state == 'in_transit':
                next_port = rec.intermediate_port_ids.filtered(
                    lambda p: p.state in ('pending', 'reached')
                )
                if next_port:
                    rec.current_port_label = next_port[0].name
                else:
                    rec.current_port_label = rec.port_of_discharge or 'Destination'
            else:
                rec.current_port_label = rec.port_of_discharge or 'Arrived'

    @api.depends('intermediate_port_ids', 'intermediate_port_ids.state')
    def _compute_has_started_moving(self):
        for rec in self:
            rec.has_started_moving = any(
                p.state in ('reached', 'passed') for p in rec.intermediate_port_ids
            )

    # ── Port pipeline helpers ─────────────────────────────────────────────────
    def _get_next_pending_port(self):
        self.ensure_one()
        return self.intermediate_port_ids.filtered(
            lambda p: p.state in ('pending', 'reached')
        )[:1]

    def _all_intermediate_ports_passed(self):
        self.ensure_one()
        ports = self.intermediate_port_ids
        return not ports or all(p.state == 'passed' for p in ports)

    # ── CRUD ──────────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('shipment.tracking') or _('New')
        return super().create(vals_list)

    # ── Smart button actions ──────────────────────────────────────────────────
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
            'type': 'ir.actions.act_window', 'name': _('Transport Trips'),
            'res_model': 'local.transport.trip', 'view_mode': 'list,form',
            'domain': [('shipment_id', '=', self.id)],
            'context': {'default_shipment_id': self.id},
        }

    def action_view_costs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Shipment Costs'),
            'res_model': 'shipment.cost', 'view_mode': 'list,form',
            'domain': [('shipment_id', '=', self.id)],
            'context': {'default_shipment_id': self.id},
        }

    def action_confirm_payment(self):
        for rec in self:
            rec.write({
                'payment_confirmed': True,
                'payment_confirmed_date': fields.Date.today(),
                'payment_confirmed_by': self.env.user.id,
            })

    def action_revoke_payment(self):
        for rec in self:
            if rec.transport_trip_ids.filtered(lambda t: t.state != 'cancelled'):
                raise UserError(_('Cannot revoke: active transport trips exist for this shipment.'))
            rec.write({
                'payment_confirmed': False,
                'payment_confirmed_date': False,
                'payment_confirmed_by': False,
            })

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

    # ── State transition actions ──────────────────────────────────────────────
    def action_set_in_transit(self):
        for rec in self:
            if rec.state != 'planned':
                raise UserError(_('Only Planned shipments can be set to In Transit.'))
            if not rec.container_ids:
                raise UserError(_('Please add at least one container before departing.'))
            rec.intermediate_port_ids.write({'state': 'pending'})
            rec.state = 'in_transit'

    def action_arrive_at_intermediate_port(self):
        """Mark the next pending intermediate port as Reached."""
        for rec in self:
            if rec.state != 'in_transit':
                raise UserError(_('Shipment must be In Transit to arrive at an intermediate port.'))
            next_port = rec._get_next_pending_port()
            if not next_port:
                discharge = rec.port_of_discharge or 'Destination Port'
                raise UserError(_(
                    'No pending intermediate ports remaining.\n'
                    'Use "Arrived at %s" to complete the shipment.'
                ) % discharge)
            next_port.write({
                'state': 'reached',
                'actual_arrival_date': next_port.actual_arrival_date or fields.Date.today(),
            })
            rec.message_post(
                body=_('Shipment reached intermediate port: <b>%s</b>') % next_port.name
            )

    def action_depart_from_intermediate_port(self):
        """Mark the currently Reached intermediate port as Passed (departed)."""
        for rec in self:
            if rec.state != 'in_transit':
                raise UserError(_('Shipment must be In Transit.'))
            reached = rec.intermediate_port_ids.filtered(lambda p: p.state == 'reached')
            if not reached:
                raise UserError(_(
                    'No intermediate port is currently at "Reached" status.\n'
                    'First use "Arrive at Intermediate Port" to mark arrival.'
                ))
            port = reached[0]
            port.state = 'passed'
            rec.message_post(
                body=_('Shipment departed from intermediate port: <b>%s</b>') % port.name
            )

    def action_set_arrived_at_destination(self):
        """Mark shipment as Arrived (directly from In Transit, merging at_port step)."""
        for rec in self:
            if rec.state != 'in_transit':
                raise UserError(_('Only In Transit shipments can be set to Arrived.'))
            if not rec._all_intermediate_ports_passed():
                pending = rec.intermediate_port_ids.filtered(lambda p: p.state != 'passed')
                names = ', '.join(pending.mapped('name'))
                raise UserError(_(
                    'The following intermediate ports have not been passed yet:\n%s\n\n'
                    'Use "Arrive at Intermediate Port" → "Depart from Intermediate Port" '
                    'for each stop.'
                ) % names)
            rec.write({
                'state': 'arrived',
                'actual_arrival_date': rec.actual_arrival_date or fields.Date.today(),
            })

    def action_reset_to_planned(self):
        for rec in self:
            if rec.state != 'in_transit':
                raise UserError(_('Only In Transit shipments can be reset to Planned.'))
            # Only allow reset if no ports have been reached/passed yet
            if any(p.state in ('reached', 'passed') for p in rec.intermediate_port_ids):
                raise UserError(_(
                    'Cannot reset: the shipment has already reached or passed intermediate ports.'
                ))
            rec.intermediate_port_ids.write({'state': 'pending'})
            rec.state = 'planned'
