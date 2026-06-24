from odoo import api, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.depends(
        'invoice_lines.move_id.state',
        'invoice_lines.quantity',
        'qty_received',
        'product_uom_qty',
        'order_id.state',
    )
    def _compute_qty_invoiced(self):
        for line in self:
            # compute qty_invoiced (unchanged from core)
            qty = 0.0
            for inv_line in line._get_invoice_lines():
                if (
                    inv_line.move_id.state not in ['cancel']
                    or inv_line.move_id.payment_state == 'invoicing_legacy'
                ):
                    if inv_line.move_id.move_type == 'in_invoice':
                        qty += inv_line.product_uom_id._compute_quantity(
                            inv_line.quantity, line.product_uom
                        )
                    elif inv_line.move_id.move_type == 'in_refund':
                        qty -= inv_line.product_uom_id._compute_quantity(
                            inv_line.quantity, line.product_uom
                        )
            line.qty_invoiced = qty

            # compute qty_to_invoice — always use ordered qty,
            # ignoring the product's purchase_method setting.
            if line.order_id.state in ['purchase', 'done']:
                line.qty_to_invoice = line.product_qty - line.qty_invoiced
            else:
                line.qty_to_invoice = 0
