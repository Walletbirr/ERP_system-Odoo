# -*- coding: utf-8 -*-
from odoo import models
from odoo.tools import float_compare


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _cim_link_sale_service_lines(self):
        """Carry the sales-side Balance onto the invoice generated from an
        order: copy the Selling Price onto the product line and link it to
        its Service Charge line, exactly as if "Balance" had been clicked on
        the invoice. Re-clicking "Balance" on the invoice then UPDATES the
        existing Service Charge line instead of adding a second one.

        Only done when the invoice holds BOTH the product line (invoiced in
        full) and its Service Charge line; otherwise the line is left alone.
        """
        service_product = self.env.ref(
            'custom_invoice_management.product_service_charge', raise_if_not_found=False
        )
        if not service_product:
            return
        for move in self.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund')):
            lines = move.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
            for line in lines.filtered(lambda l: l.product_id != service_product):
                sol = line.sale_line_ids
                if len(sol) != 1 or not sol.cim_selling_price or not sol.cim_service_line_id:
                    continue
                if float_compare(
                    line.quantity, sol.product_uom_qty,
                    precision_rounding=line.product_uom_id.rounding or 0.01,
                ) != 0:
                    continue
                service_line = lines.filtered(
                    lambda l: l.product_id == service_product
                    and sol.cim_service_line_id in l.sale_line_ids
                )
                if len(service_line) != 1:
                    continue
                line.write({
                    'cim_selling_price': sol.cim_selling_price,
                    'cim_service_line_id': service_line.id,
                })
