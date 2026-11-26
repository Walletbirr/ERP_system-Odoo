from odoo import fields, models


class PurchaseBankPayment(models.Model):
    _inherit = 'purchase.bank.payment'

    source = fields.Selection(
        selection_add=[('lc_margin', 'LC Margin (at opening)'),
                       ('lc_settlement', 'LC Settlement')],
        ondelete={'lc_margin': 'set default', 'lc_settlement': 'set default'})
    lc_id = fields.Many2one('lc.management', string="Letter of Credit",
                            readonly=True, copy=False)
    lc_settlement_line_id = fields.Many2one(
        'lc.settlement.line', string="LC Settlement", readonly=True,
        copy=False, ondelete='set null')
