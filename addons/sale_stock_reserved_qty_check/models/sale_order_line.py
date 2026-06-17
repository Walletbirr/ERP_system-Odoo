from odoo import _, models
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _get_relevant_lines(self):
        """ Lines for which a free-quantity check makes sense: real,
        storable products only (services / sections / notes / downpayments
        are excluded). """
        return self.filtered(
            lambda l: not l.display_type
            and not l.is_downpayment
            and l.product_id
            and l.product_id.type == 'consu'
            and l.product_id.is_storable
        )

    def _check_free_qty_for_lines(self, qty_override=None):
        """ Compare each line's requested quantity against the free
        (unreserved) quantity available in the order's warehouse.

        :param qty_override: if given, used as the requested quantity
            instead of each line's stored `product_uom_qty`. Useful to
            validate a quantity *before* it is actually written.
        :return: error message string, or False if all lines are fine.
        """
        lines_to_check = self._get_relevant_lines()
        if not lines_to_check:
            return False

        problems = []
        for line in lines_to_check:
            warehouse = line.order_id.warehouse_id
            if not warehouse:
                continue

            product = line.product_id.with_context(
                location=warehouse.lot_stock_id.id,
                warehouse=warehouse.id,
            )

            requested_qty = qty_override if qty_override is not None else line.product_uom_qty
            # free_qty already excludes this line's own reservation, so when
            # simulating a new quantity we add the current one back before
            # comparing, otherwise the line would appear to compete with itself.
            available_qty = product.free_qty + line.product_uom_qty if qty_override is not None else product.free_qty

            if requested_qty > available_qty:
                problems.append(_(
                    "%(product)s: requested %(requested)s, only %(available)s available",
                    product=line.product_id.display_name,
                    requested=requested_qty,
                    available=available_qty,
                ))

        if not problems:
            return False

        return _(
            "Some products do not have enough available quantity in stock:\n%(details)s",
            details="\n".join(problems),
        )

    def _get_insufficient_free_qty_message(self):
        return self._check_free_qty_for_lines()

    def _update_line_quantity(self, values):
        if 'product_uom_qty' in values:
            confirmed_lines = self.filtered(lambda l: l.order_id.state == 'sale')
            if confirmed_lines:
                error_msg = confirmed_lines._check_free_qty_for_lines(
                    qty_override=values['product_uom_qty']
                )
                if error_msg:
                    raise UserError(error_msg)
        return super()._update_line_quantity(values)
