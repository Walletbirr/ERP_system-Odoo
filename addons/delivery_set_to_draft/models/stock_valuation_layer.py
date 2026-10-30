from odoo import fields, models


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    draft_reversed = fields.Boolean(
        string='Handled by Set to Draft',
        copy=False,
        index=True,
        help="Technical flag: this layer was reversed by (or is the reversal of) a "
             "'Set to Draft' on a delivery, so it is ignored on any later Set to Draft.",
    )
