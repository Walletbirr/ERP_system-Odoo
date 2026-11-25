# /custom_addons/shipment_tracking/models/shipment_location.py

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ShipmentLocation(models.Model):
    """
    Configurable Port / Location master data.

    Replaces the old free-text Char fields "Port of Loading" and
    "Final Destination" on shipment.tracking. Users manage the list of
    Ports themselves (Shipments ▸ Configuration ▸ Ports) instead of typing
    a new string by hand on every shipment. The same list is used as the
    dropdown source for BOTH "Port of Loading" and "Final Destination" —
    a port loaded from in one shipment may well be the destination of
    another.
    """
    _name = 'shipment.location'
    _description = 'Shipment Port / Location'
    _order = 'sequence, name'

    name = fields.Char(string='Port / Location', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    notes = fields.Char(string='Description')

    @api.constrains('name')
    def _check_name_unique(self):
        """
        Soft duplicate check (Python-level, not a DB constraint), same
        pattern as shipment.carrier / shipment.cost.stage — never blocks
        install/upgrade even if duplicates already exist in the table.
        """
        for rec in self:
            if not rec.name:
                continue
            duplicate = self.search([
                ('id', '!=', rec.id),
                ('name', '=', rec.name),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    _('A Port / Location named "%s" already exists.') % rec.name
                )
