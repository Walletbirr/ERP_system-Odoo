# /custom_addons/shipment_tracking/models/container.py

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re


class ShipmentContainer(models.Model):
    _name = 'shipment.container'
    _description = 'Shipment Container'
    _rec_name = 'container_number'
    _order = 'container_number asc'

    shipment_id = fields.Many2one(
        'shipment.tracking', string='Shipment', required=True, ondelete='cascade',
    )
    container_number = fields.Char(
        string='Container Number', required=True,
        help='Standard ISO format: 4 uppercase letters + 7 digits. E.g. MSCU1234567',
    )
    size = fields.Selection([
        ('20ft',    '20 ft Standard'),
        ('40ft',    '40 ft Standard'),
        ('40ft_hc', '40 ft High Cube'),
    ], string='Container Size', required=True)
    seal_number = fields.Char(string='Seal Number')
    notes = fields.Char(string='Notes')

    shipment_state = fields.Selection(
        related='shipment_id.state', string='Shipment Status', readonly=True, store=True,
    )
    carrier = fields.Char(
        related='shipment_id.carrier', string='Carrier', readonly=True, store=True,
    )

    # FIX #3: Local transport status for this specific container
    local_transport_state = fields.Selection([
        ('not_assigned', 'Not Assigned'),
        ('pending',      'Pending'),
        ('in_transit',   'In Transit'),
        ('delivered',    'Delivered'),
    ], string='Local Transport Status',
       compute='_compute_local_transport_state',
       store=True,
       help='The current local transport status of this container '
            '(based on its truck assignment).',
    )

    @api.depends(
        'shipment_id.transport_trip_ids',
        'shipment_id.transport_trip_ids.assignment_ids.container_id',
        'shipment_id.transport_trip_ids.assignment_ids.container2_id',
        'shipment_id.transport_trip_ids.assignment_ids.state',
    )
    def _compute_local_transport_state(self):
        for rec in self:
            # Search in both container slots across all trips for this shipment
            assignment = self.env['local.transport.assignment'].search([
                ('trip_id.shipment_id', '=', rec.shipment_id.id),
                '|',
                ('container_id', '=', rec.id),
                ('container2_id', '=', rec.id),
            ], limit=1, order='id desc')

            if not assignment:
                rec.local_transport_state = 'not_assigned'
            else:
                rec.local_transport_state = assignment.state

    @api.constrains('container_number')
    def _check_container_number_format(self):
        pattern = re.compile(r'^[A-Z]{4}\d{7}$')
        for rec in self:
            cn = (rec.container_number or '').strip().upper()
            if cn and not pattern.match(cn):
                raise ValidationError(_(
                    'Container number "%s" is not valid.\n'
                    'Format must be: 4 uppercase letters + 7 digits\n'
                    'Example: MSCU1234567'
                ) % rec.container_number)

    @api.constrains('container_number', 'shipment_id')
    def _check_unique_container_in_shipment(self):
        for rec in self:
            duplicate = self.search([
                ('container_number', '=', rec.container_number),
                ('shipment_id', '=', rec.shipment_id.id),
                ('id', '!=', rec.id),
            ])
            if duplicate:
                raise ValidationError(_(
                    'Container number "%s" already exists in this shipment.'
                ) % rec.container_number)

    @api.onchange('container_number')
    def _onchange_container_number(self):
        if self.container_number:
            self.container_number = self.container_number.strip().upper()
