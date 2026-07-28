# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_new_line_matches_sale_order(vals)
        return super(AccountMoveLine, self).create(vals_list)

    def _check_new_line_matches_sale_order(self, vals):
        """Block adding a brand new product line (via 'Add a line') to an
        invoice that was generated from a Sale Order, unless that product
        actually belongs to the Sale Order. Section/note lines and lines
        that already carry a sale_line_id (i.e. created by the normal
        'Create Invoice' flow) are always allowed.
        """
        if vals.get('display_type'):
            return  # section / note line, not a product line
        if vals.get('sale_line_ids'):
            return  # legitimately generated from an SO line

        move_id = vals.get('move_id')
        product_id = vals.get('product_id')
        if not move_id or not product_id:
            return

        move = self.env['account.move'].browse(move_id)
        # Only enforce this on invoices that already have at least one
        # line traceable to a sale order - i.e. this invoice came from a SO.
        existing_sale_lines = move.invoice_line_ids.mapped('sale_line_ids')
        if not existing_sale_lines:
            return

        so = existing_sale_lines.mapped('order_id')
        so_products = set(so.order_line.filtered(lambda l: not l.display_type).mapped('product_id.id'))
        if product_id not in so_products:
            product_name = self.env['product.product'].browse(product_id).display_name
            raise UserError(_(
                "You cannot add '%(product)s' to this invoice because it is "
                "not part of Sale Order %(order)s. This invoice was "
                "generated from that order, so its lines must match. "
                "If this product was genuinely sold, add it to the Sale "
                "Order first, then re-generate/refresh the invoice line."
            ) % {
                'product': product_name,
                'order': ', '.join(so.mapped('name')),
            })

    def unlink(self):
        for line in self:
            if line.sale_line_ids:
                raise UserError(_(
                    "You cannot delete invoice line '%(product)s' because it "
                    "originates from Sale Order %(order)s. Deleting it would "
                    "make this invoice no longer match what was sold. "
                    "If the quantity is wrong, set it to 0 instead, or use a "
                    "credit note once the invoice is posted."
                ) % {
                    'product': line.product_id.display_name or line.name,
                    'order': ', '.join(line.sale_line_ids.mapped('order_id.name')),
                })
        return super(AccountMoveLine, self).unlink()

    def write(self, vals):
        locked_fields = {'product_id', 'quantity'}
        if locked_fields.intersection(vals.keys()):
            for line in self:
                if not line.sale_line_ids:
                    continue
                if 'product_id' in vals and line.product_id.id != vals['product_id']:
                    raise UserError(_(
                        "You cannot change the product on invoice line "
                        "'%(product)s' because it originates from Sale Order "
                        "%(order)s. Add a new line for the different product "
                        "instead."
                    ) % {
                        'product': line.product_id.display_name or line.name,
                        'order': ', '.join(line.sale_line_ids.mapped('order_id.name')),
                    })
                if 'quantity' in vals and line.quantity != vals['quantity']:
                    raise UserError(_(
                        "You cannot change the quantity on invoice line "
                        "'%(product)s' because it originates from Sale Order "
                        "%(order)s. The invoiced quantity must reflect what "
                        "was actually delivered/sold. If it's wrong, correct "
                        "it via the Sale Order or a credit note, not by "
                        "editing this line directly."
                    ) % {
                        'product': line.product_id.display_name or line.name,
                        'order': ', '.join(line.sale_line_ids.mapped('order_id.name')),
                    })
        return super(AccountMoveLine, self).write(vals)
