from odoo import models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        res = super().action_post()

        for payment in self:
            # Only outbound payments to vendors
            if payment.payment_type != 'outbound' or payment.partner_type != 'supplier':
                continue

            # Find the vendor bill(s) this payment reconciles against.
            # reconciled_invoice_ids is the standard Odoo field linking a
            # payment to the bills it settles, populated once reconciliation
            # happens (which for the "Register Payment" wizard happens
            # immediately on posting).
            bills = payment.reconciled_invoice_ids.filtered(
                lambda b: b.move_type == 'in_invoice'
            )

            for bill in bills:
                purchase = self.env['purchase.order'].search([
                    ('name', '=', bill.invoice_origin)
                ], limit=1)

                if not purchase or not purchase.lc_id:
                    continue

                lc = purchase.lc_id
                if lc.state in ('closed', 'cancelled'):
                    continue

                # One settlement line per PAYMENT (not per bill), since a
                # single bill may be paid in several installments over time.
                lc._create_draft_settlement_line_for_payment(purchase, bill, payment)

        return res
