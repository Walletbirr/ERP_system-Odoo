from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_vehicle = fields.Boolean(string="Is a Vehicle")
    engine_number = fields.Char(string="Engine Number")