from odoo import fields, models


class VehicleIdDocumentType(models.Model):
    _name = 'vehicle.id.document.type'
    _description = 'ID Document Type (Document Tracking Configuration)'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(
        default=True,
        help="Uncheck to hide this type from selection without deleting "
             "it - keeps it intact on any collection record that already "
             "uses it.",
    )