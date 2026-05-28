from odoo import models, fields


class AccountAccount(models.Model):
    _inherit = 'account.account'

    current_balance = fields.Float(
        compute='_compute_current_balance',
        string='Balance'
    )

    def _compute_current_balance(self):

        balances = {
            account.id: balance
            for account, balance in self.env['account.move.line']._read_group(
                domain=[
                    ('account_id', 'in', self.ids),
                    ('parent_state', '=', 'posted')
                ],
                groupby=['account_id'],
                aggregates=['balance:sum'],
            )
        }

        for record in self:

            balance = balances.get(record.id, 0)

            # Reverse sign for credit-natural accounts
            if record.internal_group in ('liability', 'equity', 'income'):
                balance = -balance

            record.current_balance = balance