from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrderPaymentProofBank(models.Model):
    """One bank / cash journal the customer's payment was deposited in,
    with the amount deposited there. An approved payment proof has one
    line per bank (before, it only had a single payment journal)."""
    _name = 'sale.order.payment.proof.bank'
    _description = 'Payment Proof - Bank Deposit'
    _order = 'sequence, id'

    proof_id = fields.Many2one(
        'sale.order.payment.proof', string='Payment Proof',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    journal_id = fields.Many2one(
        'account.journal', string='Bank', required=True,
        domain="[('type', 'in', ('bank', 'cash'))]")
    currency_id = fields.Many2one(
        related='proof_id.sale_order_id.currency_id', string='Currency')
    amount = fields.Monetary(
        string='Amount', required=True, currency_field='currency_id')

    _sql_constraints = [
        ('proof_journal_uniq', 'unique(proof_id, journal_id)',
         'The same bank can only be listed once per payment proof.'),
    ]

    @api.constrains('amount')
    def _check_amount_positive(self):
        for line in self:
            if line.currency_id.compare_amounts(line.amount, 0) <= 0:
                raise ValidationError(_(
                    "The amount deposited in %s must be greater than zero.",
                    line.journal_id.display_name))
