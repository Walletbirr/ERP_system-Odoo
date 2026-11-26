from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        for move in self.filtered(lambda m: m.move_type == 'in_invoice'):
            pos = move.invoice_line_ids.purchase_line_id.order_id
            direct = pos.filtered('x_direct_pay')
            if direct:
                raise UserError(_(
                    "%s is paid directly from the bank, so it cannot have a "
                    "vendor bill. Untick 'Pay Directly From Bank' on the "
                    "purchase order if this supplier is paid on credit.",
                    ", ".join(direct.mapped('name'))))
        return super()._post(soft=soft)
