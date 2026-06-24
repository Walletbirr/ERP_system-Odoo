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

            # Must have LC
            lc = purchase.lc_id
            if not lc:
                continue

            # Don't create settlement lines on closed/cancelled LCs
            if lc.state in ('closed', 'cancelled'):
                continue

            # Creates a DRAFT settlement line only - no accounting move yet.
            # A person reviews/confirms it from the LC's Settlement tab,
            # which is what actually posts the fee/VAT and margin-release entries.
            lc._create_draft_settlement_line(purchase, move)

        return res
