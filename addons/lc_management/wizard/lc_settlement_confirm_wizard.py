from odoo import models, fields


class LCSettlementConfirmWizard(models.TransientModel):
    _name = 'lc.settlement.confirm.wizard'
    _description = 'LC Settlement Confirmation'

    settlement_line_id = fields.Many2one('lc.settlement.line', required=True, readonly=True)
    preview_text = fields.Text(string="Entries to be posted", readonly=True)

    def action_confirm_settlement(self):
        self.ensure_one()
        notification = self.settlement_line_id.action_confirm()

        # action_confirm may return a toast-notification action when margin
        # was released. We close THIS dialog regardless, and chain the
        # notification as a follow-up client action so it doesn't get
        # mistaken for content rendered inside the now-closed wizard.
        if notification and notification.get('tag') == 'display_notification':
            notification['params']['next'] = {'type': 'ir.actions.act_window_close'}
            return notification

        return {'type': 'ir.actions.act_window_close'}
