from odoo import models, fields


class LCSettlementConfirmWizard(models.TransientModel):
    _name = 'lc.settlement.confirm.wizard'
    _description = 'LC Settlement Confirmation'

    settlement_line_id = fields.Many2one('lc.settlement.line', required=True, readonly=True)
    preview_text = fields.Text(string="Entries to be posted", readonly=True)

    def action_confirm_settlement(self):
        self.ensure_one()
        self.settlement_line_id.action_confirm()
        return {'type': 'ir.actions.act_window_close'}
