from odoo import models, fields


class LCOpenRequestWizard(models.TransientModel):
    _name = 'lc.open.request.wizard'
    _description = 'Send LC Opening Request to Accountant'

    lc_id = fields.Many2one('lc.management', required=True, readonly=True)
    accountant_id = fields.Many2one(
        'res.users',
        string="Send To",
        required=True,
        default=lambda self: self.env.company.lc_default_accountant_id,
        help="The accountant who will review and approve opening this LC."
    )
    note = fields.Text(
        string="Note",
        help="Optional message included with the notification, e.g. anything the "
             "accountant should double check before approving."
    )

    def action_send(self):
        self.ensure_one()
        self.lc_id._send_opening_request(self.accountant_id, self.note)
        return {'type': 'ir.actions.act_window_close'}
