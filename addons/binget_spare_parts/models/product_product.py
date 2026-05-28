from odoo import models, fields


class ProductProduct(models.Model):
    """Expose product_model at the variant level so BoM
    lines and other models can reference it directly."""

    _inherit = 'product.product'

    product_model = fields.Char(
        string='Product Model',
        related='product_tmpl_id.product_model',
        store=True,
        readonly=True,
    )