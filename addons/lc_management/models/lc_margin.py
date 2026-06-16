from odoo import models, fields, api
from odoo.exceptions import ValidationError

class LCMargin(models.Model):
    _name = 'lc.margin'
    _description = 'LC margin'

    name = fields.Char(required=True)

    margin_percentage = fields.Float(
        string="Margin Percentage",
        required=True
    )

    active = fields.Boolean(default=True)

