from odoo import models, fields
from odoo.exceptions import ValidationError


class LCOpenConfirmWizard(models.TransientModel):
    _name = 'lc.open.confirm.wizard'
    _description = 'LC Open Confirmation'

    lc_id = fields.Many2one('lc.management', required=True, readonly=True)
    preview_text = fields.Text(string="Moves to be posted", readonly=True)

    def action_confirm_open(self):
        self.ensure_one()
        self.lc_id.action_open()
        return {'type': 'ir.actions.act_window_close'}
