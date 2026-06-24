from odoo import models, fields

class LCCancelWizard(models.TransientModel):
    _name = 'lc.cancel.wizard'
    _description = 'LC Cancel Wizard'

    lc_id = fields.Many2one(
        'lc.management',
        required=True
    )

    reason = fields.Text(
        string="Cancellation Reason",
        required=True
    )

    def action_confirm_cancel(self):
        self.ensure_one()

        self.lc_id.write({
            'cancel_reason': self.reason
        })

        self.lc_id.action_cancel_lc()

        return {'type': 'ir.actions.act_window_close'}
