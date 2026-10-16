from odoo import fields, models


class PaymentProofRejectWizard(models.TransientModel):
    _name = 'sale.order.payment.proof.reject.wizard'
    _description = 'Reject Payment Proof'

    # Explicit short relation: the auto-generated name from the two long
    # model names exceeds PostgreSQL's 63-character identifier limit.
    proof_ids = fields.Many2many(
        'sale.order.payment.proof',
        'payment_proof_reject_wiz_rel', 'wizard_id', 'proof_id',
        string='Payment Proofs',
        required=True,
    )
    reason = fields.Text(
        string='Reason for Rejection',
        required=True,
        help="Shown to the salesperson so they know what to fix before "
             "resubmitting.",
    )

    def action_reject(self):
        self.ensure_one()
        self.proof_ids.action_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
