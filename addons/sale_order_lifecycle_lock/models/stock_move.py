# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_new_move_matches_sale_order(vals)
        return super(StockMove, self).create(vals_list)

    def _check_new_move_matches_sale_order(self, vals):
        """Block adding a brand new product line (via 'Add a line') to a
        delivery that originates from a Sale Order, unless that product is
        actually on the Sale Order. Moves created by the normal SO -> stock
        rule flow already carry sale_line_id and are left untouched.
        """
        if vals.get('sale_line_id'):
            return  # created normally from the SO confirmation flow

        picking_id = vals.get('picking_id')
        product_id = vals.get('product_id')
        if not picking_id or not product_id:
            return

        picking = self.env['stock.picking'].browse(picking_id)
        sale_order = picking.sale_id
        if not sale_order:
            return  # this delivery isn't tied to a sale order at all

        so_products = set(sale_order.order_line.filtered(lambda l: not l.display_type).mapped('product_id.id'))
        if product_id not in so_products:
            product_name = self.env['product.product'].browse(product_id).display_name
            raise UserError(_(
                "You cannot add '%(product)s' to this delivery because it is "
                "not part of Sale Order %(order)s. A delivery must only ship "
                "what was actually sold. If this product was genuinely sold, "
                "add it to the Sale Order first."
            ) % {
                'product': product_name,
                'order': sale_order.name,
            })

    def unlink(self):
        for move in self:
            if move.sale_line_id and move.state != 'cancel':
                raise UserError(_(
                    "You cannot delete the delivery line '%(product)s' "
                    "because it originates from Sale Order %(order)s. "
                    "If this product should not be delivered, set the "
                    "quantity to 0 or cancel the whole transfer instead."
                ) % {
                    'product': move.product_id.display_name,
                    'order': move.sale_line_id.order_id.name,
                })
        return super(StockMove, self).unlink()

    def write(self, vals):
        locked_fields = {'product_id', 'product_uom_qty'}
        if locked_fields.intersection(vals.keys()):
            for move in self:
                if not move.sale_line_id:
                    continue
                if 'product_id' in vals and move.product_id.id != vals['product_id']:
                    raise UserError(_(
                        "You cannot change the product on delivery line "
                        "'%(product)s' because it originates from Sale Order "
                        "%(order)s. Add a new line instead."
                    ) % {
                        'product': move.product_id.display_name,
                        'order': move.sale_line_id.order_id.name,
                    })
                if 'product_uom_qty' in vals and move.product_uom_qty != vals['product_uom_qty']:
                    raise UserError(_(
                        "You cannot change the demand quantity on delivery "
                        "line '%(product)s' because it originates from Sale "
                        "Order %(order)s. The demand must reflect what was "
                        "sold. If the SO quantity was wrong, correct it on "
                        "the Sale Order itself - the delivery will follow. "
                        "The actual delivered quantity (partial delivery / "
                        "backorder) can still be set normally at pick time."
                    ) % {
                        'product': move.product_id.display_name,
                        'order': move.sale_line_id.order_id.name,
                    })
        return super(StockMove, self).write(vals)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        self._check_moves_match_sale_order()
        return super(StockPicking, self).button_validate()

    def _check_moves_match_sale_order(self):
        """Belt-and-suspenders check kept from before: even though new
        mismatched lines are now blocked at creation time, this still
        catches anything created via import, API, or other bypass paths.
        """
        for picking in self:
            sale_order = picking.sale_id
            if not sale_order:
                continue

            so_products = set(sale_order.order_line.filtered(
                lambda l: not l.display_type
            ).mapped('product_id.id'))

            move_products = set(picking.move_ids.filtered(
                lambda m: m.state != 'cancel'
            ).mapped('product_id.id'))

            extra_products = move_products - so_products
            if extra_products:
                extra_names = self.env['product.product'].browse(list(extra_products)).mapped('display_name')
                raise UserError(_(
                    "This delivery includes product(s) that are not on the "
                    "originating Sale Order %(order)s: %(products)s.\n\n"
                    "A delivery must only ship what was actually sold. "
                    "Please remove the extra product(s), or add them to the "
                    "Sale Order first if they were genuinely sold."
                ) % {
                    'order': sale_order.name,
                    'products': ', '.join(extra_names),
                })
