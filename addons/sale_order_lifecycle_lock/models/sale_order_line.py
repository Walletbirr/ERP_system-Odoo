# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError

# States in which a sale order is considered "confirmed" and therefore locked.
LOCKED_SO_STATES = ('sale', 'done')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def unlink(self):
        for line in self:
            if line.order_id.state in LOCKED_SO_STATES:
                raise UserError(_(
                    "You cannot delete the line '%(product)s' from confirmed "
                    "Sale Order %(order)s. The order has already been confirmed "
                    "and this line may be tied to deliveries or invoices. "
                    "If this was added by mistake, cancel the order instead, "
                    "or contact an administrator."
                ) % {
                    'product': line.product_id.display_name or line.name,
                    'order': line.order_id.name,
                })
        return super(SaleOrderLine, self).unlink()

    def write(self, vals):
        if 'product_id' in vals:
            for line in self:
                if line.order_id.state in LOCKED_SO_STATES and line.product_id.id != vals['product_id']:
                    raise UserError(_(
                        "You cannot change the product on line '%(product)s' "
                        "in confirmed Sale Order %(order)s. If the customer "
                        "wants a different product, add a new line instead so "
                        "there is a clear record of the change."
                    ) % {
                        'product': line.product_id.display_name or line.name,
                        'order': line.order_id.name,
                    })
        return super(SaleOrderLine, self).write(vals)
