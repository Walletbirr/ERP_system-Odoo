from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _confirmation_error_message(self):
        error_msg = super()._confirmation_error_message()
        if error_msg:
            return error_msg

        return self.order_line._get_insufficient_free_qty_message()
