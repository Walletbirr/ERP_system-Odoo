# /custom_addons/shipment_tracking/models/shipment_port.py

from odoo import models, fields, _
from odoo.exceptions import UserError


class ShipmentPort(models.Model):
    _name = 'shipment.port'
    _description = 'Intermediate Port / Transshipment Hub'
    _order = 'sequence, id'

    shipment_id = fields.Many2one(
        'shipment.tracking', string='Shipment',
        required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(string='Order', default=10)
    name = fields.Char(string='Port Name', required=True)
    arrival_date = fields.Date(string='Expected Arrival')
    actual_arrival_date = fields.Date(string='Actual Arrival')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('reached', 'Reached'),
        ('passed',  'Passed'),
    ], string='Status', default='pending')
    notes = fields.Char(string='Notes')

    def action_delete_port(self):
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_(
                    'Port "%s" cannot be deleted because its status is "%s". '
                    'Only Pending ports can be removed.'
                ) % (rec.name, dict(self._fields['state'].selection).get(rec.state)))
        return self.unlink()

    def unlink(self):
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_(
                    'Port "%s" cannot be deleted because its status is "%s". '
                    'Only Pending ports can be removed.'
                ) % (rec.name, dict(self._fields['state'].selection).get(rec.state)))
        return super().unlink()
