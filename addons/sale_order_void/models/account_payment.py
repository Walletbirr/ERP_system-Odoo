from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _name = 'account.payment'
    _inherit = ['account.payment', 'sale.void.mixin']

    x_void_order_id = fields.Many2one(
        'sale.order', string='Voided With Order', copy=False, readonly=True)
    x_void_original_amount = fields.Monetary(
        string='Amount Before Void', currency_field='currency_id',
        copy=False, readonly=True)

    def action_draft(self):
        if (not self.env.context.get('sale_order_void')
                and any(p.x_is_voided for p in self)):
            raise UserError(_(
                "A voided payment cannot be set back to draft."))
        return super().action_draft()
