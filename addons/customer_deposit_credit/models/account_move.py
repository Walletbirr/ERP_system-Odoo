from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super().action_post()
        self._trigger_deposit_recompute()
        return res

    def button_cancel(self):
        res = super().button_cancel()
        self._trigger_deposit_recompute()
        return res

    def _trigger_deposit_recompute(self):
        invoices = self.filtered(lambda m: m.move_type == 'out_invoice')
        partners = invoices.mapped('partner_id').filtered(lambda p: p.id)
        if partners:
            partners._compute_deposit_amounts()
