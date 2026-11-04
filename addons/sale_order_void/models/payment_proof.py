from odoo import fields, models


class SaleOrderPaymentProof(models.Model):
    _inherit = 'sale.order.payment.proof'

    # A real Void status for the proof of a voided sale (it is not
    # "Rejected": the proof was valid, the sale was voided afterwards).
    state = fields.Selection(
        selection_add=[('void', 'Void')],
        ondelete={'void': 'set default'})
