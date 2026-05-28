from odoo import models, fields


class ProductTemplate(models.Model):
    """Extend product.template with an optional Product Model
    field. Used to group products by manufacturing model code
    e.g. HH150ZH, HH200ZH. Leave blank for universal parts."""

    _inherit = 'product.template'

    product_model = fields.Char(
        string='Product Model',
        help='Enter the model code this product belongs to.\n'
             'Examples: HH150ZH  |  HH200ZH  |  HH150ZH / HH200ZH\n'
             'Leave blank for universal or generic products.',
        placeholder='e.g. HH150ZH',
        index=True,
    )