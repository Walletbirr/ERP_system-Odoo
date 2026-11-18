from odoo import models, api


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.model_create_multi
    def create(self, vals_list):
        accounts = super().create(vals_list)
        accounts._lc_autolink_as_fee_account()
        return accounts

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals or 'code' in vals:
            self._lc_autolink_as_fee_account()
        return res

    def _lc_autolink_as_fee_account(self):
        """The counterpart to lc.management._autolink_fee_account(): fires
        whenever a GL account is created or renamed, so a fee account set
        up *before* its LC even exists still gets picked up correctly -
        the moment that LC is created (or its reference is set/changed),
        it will find this account by the same name match.

        Matching is purely by reference (LC's `name` appearing in the
        account's `name`, case-insensitive) - deliberately not driven by
        any company-wide default, since each LC needs its own distinct
        fee account.
        """
        LC = self.env['lc.management'].sudo()
        for account in self:
            if not account.name:
                continue
            pending_lcs = LC.search([('opening_fee_account_id', '=', False)])
            for lc in pending_lcs:
                if lc.name and lc.name.lower() in account.name.lower():
                    lc.opening_fee_account_id = account.id
