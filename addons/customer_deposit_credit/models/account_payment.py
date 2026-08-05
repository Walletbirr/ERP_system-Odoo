from odoo import models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        res = super().action_post()
        self._trigger_deposit_recompute()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        self._trigger_deposit_recompute()
        return res

    def _trigger_deposit_recompute(self):
        partners = self.mapped('partner_id').filtered(lambda p: p.id)
        if partners:
            partners._compute_deposit_amounts()
