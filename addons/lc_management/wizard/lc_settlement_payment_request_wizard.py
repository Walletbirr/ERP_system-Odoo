from odoo import models, fields


class LCSettlementPaymentRequestWizard(models.TransientModel):
    _name = 'lc.settlement.payment.request.wizard'
    _description = 'Send LC Settlement Payment Request to Accountant'

    settlement_line_id = fields.Many2one('lc.settlement.line', required=True, readonly=True)
    accountant_id = fields.Many2one(
        'res.users',
        string="Send To",
        required=True,
        default=lambda self: self.env.company.lc_default_accountant_id,
        help="The accountant who will review and approve this payment."
    )
    note = fields.Text(
        string="Note",
        help="Optional message included with the notification."
    )

    def action_send(self):
        self.ensure_one()
        self.settlement_line_id._send_payment_request(self.accountant_id, self.note)
        return {'type': 'ir.actions.act_window_close'}
