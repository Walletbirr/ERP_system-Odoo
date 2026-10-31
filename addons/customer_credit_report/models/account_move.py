from odoo import api, fields, models
from odoo.tools.sql import column_exists, create_column

from .sale_order import SALE_TYPES


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_sale_type = fields.Selection(
        SALE_TYPES, string='Sale Type', tracking=True, index=True,
        compute='_compute_x_sale_type', store=True, readonly=True,
        precompute=True, recursive=True,
        help="Credit invoices are followed in Sales > Reporting > Customer "
             "Credit. Taken from the sales order(s); on an invoice without "
             "an order, from its payment term (ticked Credit Sale).")

    def _auto_init(self):
        # Create the column ourselves so Odoo does not compute the sale
        # type for every existing journal entry through the ORM on
        # install: the post-init hook / migration fills it in SQL.
        if not column_exists(self.env.cr, 'account_move', 'x_sale_type'):
            create_column(self.env.cr, 'account_move', 'x_sale_type',
                          'varchar')
        return super()._auto_init()

    @api.depends('move_type', 'invoice_payment_term_id',
                 'invoice_line_ids.sale_line_ids.order_id.x_sale_type',
                 'reversed_entry_id.x_sale_type')
    def _compute_x_sale_type(self):
        for move in self:
            if move.move_type not in ('out_invoice', 'out_refund'):
                move.x_sale_type = False
                continue
            orders = move.invoice_line_ids.sale_line_ids.order_id
            if orders:
                move.x_sale_type = ('credit' if 'credit' in
                                    orders.mapped('x_sale_type') else 'cash')
            elif move.reversed_entry_id.x_sale_type:
                move.x_sale_type = move.reversed_entry_id.x_sale_type
            else:
                move.x_sale_type = ('credit'
                                    if move.invoice_payment_term_id.x_is_credit
                                    else 'cash')
