from odoo import api, fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    x_requires_document_tracking = fields.Boolean(
        string='Track Document Release',
        help="If checked, invoice lines for products in this category "
             "(e.g. Vehicles) will be tracked through the Document Release "
             "workflow: locked until the invoice is fully paid, then "
             "flagged as Ready for Collection until someone marks the "
             "document as physically handed over.",
    )
    x_effective_document_tracking = fields.Boolean(
        string='Document Tracking (incl. inherited)',
        compute='_compute_x_effective_document_tracking', store=True,
        recursive=True,
        help="True if this category or ANY parent category above it has "
             "'Track Document Release' checked. This is what the module "
             "actually uses - so ticking the box once on a parent category "
             "like 'Vehicles' covers every subcategory beneath it "
             "automatically.",
    )

    @api.depends('x_requires_document_tracking', 'parent_id.x_effective_document_tracking')
    def _compute_x_effective_document_tracking(self):
        for categ in self:
            if categ.x_requires_document_tracking:
                categ.x_effective_document_tracking = True
            else:
                categ.x_effective_document_tracking = bool(
                    categ.parent_id and categ.parent_id.x_effective_document_tracking
                )

