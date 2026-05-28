from odoo import models, fields


class MrpBomLine(models.Model):
    """Expose product_model on BoM component lines,
    pulled from the linked product template.
    Read-only — value is set on the product itself."""

    _inherit = 'mrp.bom.line'

    product_model = fields.Char(
        string='Model',
        related='product_id.product_tmpl_id.product_model',
        store=False,
        readonly=True,
    )