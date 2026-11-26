from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class LCSettlementSplitWizard(models.TransientModel):
    """Split one settlement into as many tranches as needed, in one go."""
    _name = 'lc.settlement.split.wizard'
    _description = 'Split Settlement Into Tranches'

    settlement_line_id = fields.Many2one(
        'lc.settlement.line', required=True, readonly=True)
    lc_currency_id = fields.Many2one(
        related='settlement_line_id.lc_currency_id', readonly=True)
    purchase_order_id = fields.Many2one(
        related='settlement_line_id.purchase_order_id', readonly=True)
    current_amount = fields.Monetary(
        related='settlement_line_id.amount_to_settle',
        currency_field='lc_currency_id', string="Amount to Split",
        readonly=True)
    part_ids = fields.One2many(
        'lc.settlement.split.wizard.part', 'wizard_id', string="Tranches")
    quick_count = fields.Integer(
        string="Split Equally Into", default=2,
        help="Fills the table with this many equal tranches. You can then "
             "change any amount, date or rate.")
    allocated = fields.Monetary(
        compute='_compute_totals', currency_field='lc_currency_id')
    remainder = fields.Monetary(
        string="Left Over", compute='_compute_totals',
        currency_field='lc_currency_id',
        help="Not allocated above. It stays as one more tranche to settle "
             "later.")

    @api.depends('part_ids.amount', 'current_amount')
    def _compute_totals(self):
        for wiz in self:
            wiz.allocated = sum(wiz.part_ids.mapped('amount'))
            wiz.remainder = wiz.current_amount - wiz.allocated

    def _equal_parts(self, count):
        """Equal tranches; the last one absorbs the rounding."""
        self.ensure_one()
        cur = self.lc_currency_id
        total = self.current_amount
        base = cur.round(total / count)
        amounts = [base] * (count - 1) + [total - base * (count - 1)]
        return [(0, 0, {'sequence': i, 'amount': a,
                        'date': fields.Date.today()})
                for i, a in enumerate(amounts, start=1)]

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        for wiz in wizards.filtered(lambda w: not w.part_ids):
            wiz.part_ids = wiz._equal_parts(2)
        return wizards

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Split Into Tranches',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_quick_split(self):
        self.ensure_one()
        if self.quick_count < 2 or self.quick_count > 60:
            raise ValidationError("Choose between 2 and 60 tranches.")
        self.part_ids = [(5, 0, 0)] + self._equal_parts(self.quick_count)
        return self._reopen()

    def action_confirm_split(self):
        self.ensure_one()
        parts = [{'amount': p.amount, 'date': p.date, 'rate': p.rate}
                 for p in self.part_ids.sorted('sequence')]
        line = self.settlement_line_id
        line._split_into(parts)
        root = line._get_root_line()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Settlement',
            'res_model': 'lc.settlement.line',
            'view_mode': 'form',
            'res_id': root.id if root.split_line_ids else line.id,
            'target': 'current',
        }


class LCSettlementSplitWizardPart(models.TransientModel):
    _name = 'lc.settlement.split.wizard.part'
    _description = 'Split Settlement Tranche'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'lc.settlement.split.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    lc_currency_id = fields.Many2one(
        related='wizard_id.lc_currency_id', readonly=True)
    amount = fields.Monetary(
        currency_field='lc_currency_id', required=True)
    percent = fields.Float(
        string="% of Total", compute='_compute_percent', digits=(5, 1))
    date = fields.Date(string="Settlement Date",
                       default=fields.Date.today)
    rate = fields.Float(
        string="Rate", digits=(12, 4),
        help="Leave empty to use the rate of the line being split.")

    @api.depends('amount', 'wizard_id.current_amount')
    def _compute_percent(self):
        for part in self:
            total = part.wizard_id.current_amount
            part.percent = part.amount / total * 100.0 if total else 0.0
