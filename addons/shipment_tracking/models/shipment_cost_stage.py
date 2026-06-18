# /custom_addons/shipment_tracking/models/shipment_cost_stage.py

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ShipmentCostStage(models.Model):
    """
    Configurable Cost Stage master data.

    Replaces the old hard-coded Selection field on shipment.cost.
    Users can now create, rename, reorder, or archive cost stages
    from the UI (Costs ▸ Configuration ▸ Cost Stages) instead of being
    limited to a fixed list defined in code.
    """
    _name = 'shipment.cost.stage'
    _description = 'Shipment Cost Stage'
    _order = 'sequence, id'

    name = fields.Char(string='Cost Stage', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    notes = fields.Char(string='Description')

    @api.constrains('name')
    def _check_name_unique(self):
        """
        Soft duplicate check (Python-level, not a DB constraint).
        Runs only when a user creates/renames a stage from the UI, so it
        can never block module installation/upgrade if a duplicate already
        exists in the table from before this field was added.
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
                    _('A Cost Stage named "%s" already exists.') % rec.name
                )
