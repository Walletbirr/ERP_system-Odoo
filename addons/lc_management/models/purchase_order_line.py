from odoo import models, api


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.depends(
        'invoice_lines.move_id.state',
        'invoice_lines.quantity',
        'qty_received',
        'product_uom_qty',
        'order_id.state',
        'order_id.lc_id',
    )
    def _compute_qty_invoiced(self):
        """Full reimplementation of Odoo's standard logic (see
        odoo/addons/purchase/models/purchase_order_line.py), with one added
        branch: for a Purchase Order linked to an LC whose shipment has
        reached its final destination, the line is billable in full
        regardless of qty_received - i.e. regardless of whether the
        warehouse has physically validated the stock transfer yet.

        This is a full override (no super() call) rather than a
        patch-after-super, because writing to qty_to_invoice after calling
        super() risked being silently undone by the ORM's own recompute of
        the same stored field on the next flush.
        """
        shipment_model = self.env['shipment.tracking'] if 'shipment.tracking' in self.env else None

        for line in self:
            # ---- qty_invoiced: unchanged, identical to Odoo's standard logic ----
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

            # ---- qty_to_invoice: standard logic, with the LC/shipment exception ----
            if line.order_id.state in ('purchase', 'done'):
                lc_shipment_arrived = False

                po = line.order_id
                if po.lc_id and shipment_model is not None:
                    shipment = shipment_model.search([
                        ('purchase_order_id', '=', po.id)
                    ], limit=1)
                    lc_shipment_arrived = bool(shipment and shipment.state == 'arrived')

                if lc_shipment_arrived:
                    # Billing eligibility satisfied by shipment arrival,
                    # not by warehouse-validated qty_received.
                    line.qty_to_invoice = max(line.product_qty - line.qty_invoiced, 0.0)
                elif line.product_id.purchase_method == 'purchase':
                    line.qty_to_invoice = line.product_qty - line.qty_invoiced
                else:
                    line.qty_to_invoice = line.qty_received - line.qty_invoiced
            else:
                line.qty_to_invoice = 0
