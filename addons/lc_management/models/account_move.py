from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super().action_post()

        for move in self:
            # Only Vendor Bills
            if move.move_type != 'in_invoice':
                continue

            # Find related PO
            purchase = self.env['purchase.order'].search([
                ('name', '=', move.invoice_origin)
            ], limit=1)

            if not purchase:
                continue

            lc = purchase.lc_id
            if not lc:
                continue

            # Settlement lines are created from the shipment's "Arrived at
            # Destination" action (see shipment_tracking.py), not here - a
            # vendor bill posting on its own does not create or post any
            # settlement accounting. This hook only attaches the bill onto
            # any settlement line(s) for this PO so it shows up for
            # reference (vendor_bill_id) when someone reviews the LC.
            lines = lc.settlement_line_ids.filtered(
                lambda l: l.purchase_order_id.id == purchase.id and not l.vendor_bill_id
            )
            if lines:
                lines.write({'vendor_bill_id': move.id})

        return res
