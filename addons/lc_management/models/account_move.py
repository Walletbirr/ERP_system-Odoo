from odoo import models, fields
from odoo.exceptions import ValidationError


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

            # Prevent duplicate release
            if lc.state == 'closed':
                continue
            if lc.release_move_id:
                continue
            bank_account = lc.bank_journal_id.default_account_id

            if not bank_account:
                raise ValidationError(
                    "Bank journal missing default account."
                )

            amount = lc.margin_amount_company_currency

            # =========================
            # RELEASE LC COLLATERAL
            # =========================
            release_move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': lc.bank_journal_id.id,
                'ref': f"LC Release - {lc.name}",
                'line_ids': [

                    # DR BANK
                    (0, 0, {
                        'name': f"LC Release - {lc.name}",
                        'account_id': bank_account.id,
                        'debit': amount,
                        'credit': 0.0,
                    }),

                    # CR LC MARGIN
                    (0, 0, {
                        'name': f"LC Release - {lc.name}",
                        'account_id': lc.margin_account_id.id,
                        'debit': 0.0,
                        'credit': amount,
                    }),
                ]
            })

            release_move.action_post()

            lc.release_move_id = release_move.id    