from odoo import models, fields


class LCSettlementSplitWizard(models.TransientModel):
    _name = 'lc.settlement.split.wizard'
    _description = 'Split Settlement Line Into Partial Payment'

    settlement_line_id = fields.Many2one('lc.settlement.line', required=True, readonly=True)
    lc_currency_id = fields.Many2one(related='settlement_line_id.lc_currency_id', readonly=True)
    current_amount = fields.Monetary(
        related='settlement_line_id.amount_to_settle',
        currency_field='lc_currency_id',
        string="Current Amount on This Line",
        readonly=True,
    )
    split_amount = fields.Monetary(
        string="Amount to Settle Now",
        currency_field='lc_currency_id',
        required=True,
        help="The portion of the current amount you want to settle in this partial "
             "payment. The remainder will stay on the original line until paid off."
    )

    def action_confirm_split(self):
        self.ensure_one()
        new_line = self.settlement_line_id._split_off_amount(self.split_amount)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Partial Settlement',
            'res_model': 'lc.settlement.line',
            'view_mode': 'form',
            'res_id': new_line.id,
            'target': 'current',
        }
