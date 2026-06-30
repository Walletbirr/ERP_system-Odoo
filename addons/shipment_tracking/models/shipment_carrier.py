# /custom_addons/shipment_tracking/models/shipment_carrier.py

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ShipmentCarrier(models.Model):
    """
    Configurable Carrier / Shipping Line master data.

    Replaces the old free-text Char field on shipment.tracking.
    Users manage the list of Carriers themselves
    (Shipments ▸ Configuration ▸ Carriers) instead of typing a new
    string by hand on every shipment.
    """
    _name = 'shipment.carrier'
    _description = 'Shipment Carrier / Shipping Line'
    _order = 'sequence, name'

    name = fields.Char(string='Carrier / Shipping Line', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    notes = fields.Char(string='Description')

    @api.constrains('name')
    def _check_name_unique(self):
        """
        Soft duplicate check (Python-level, not a DB constraint), same
        pattern as shipment.cost.stage — never blocks install/upgrade
        even if duplicates already exist in the table.
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
                    _('A Carrier named "%s" already exists.') % rec.name
                )
