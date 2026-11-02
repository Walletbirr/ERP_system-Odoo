from odoo import api, fields, models

from . import trace
from .account_move import MANUAL_CONTEXT


def _drop_stale_amount_currency(vals):
    """The web form sends amount_currency = 0 for a line whose debit/credit
    was typed. Odoo then lets that 0 win and the line is stored as 0.00.
    Dropping it lets Odoo derive the amount in the line currency from the
    typed debit/credit."""
    if 'amount_currency' not in vals or vals['amount_currency']:
        return vals
    typed = any(vals.get(key) for key in ('debit', 'credit', 'balance'))
    if typed:
        vals = {k: v for k, v in vals.items() if k != 'amount_currency'}
    return vals


def _flag_manual_line(vals):
    """A line typed in the Journal Items tab: amounts but no price/product."""
    if 'ile_manual_line' in vals:
        return vals
    typed = any(vals.get(key) for key in ('debit', 'credit', 'balance'))
    if typed and not vals.get('price_unit') and not vals.get('product_id'):
        vals = dict(vals, ile_manual_line=True)
    return vals


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    ile_manual_line = fields.Boolean(
        string='Manual Journal Line',
        copy=False,
        help="Typed directly in the Journal Items tab of an invoice in manual "
             "mode. Such a line has no price or quantity, so it is not shown "
             "in the Invoice Lines tab.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        moves = self.env['account.move'].browse(
            [vals['move_id'] for vals in vals_list if vals.get('move_id')]
        )
        manual = moves.filtered('manual_journal_items')
        if not manual:
            return super().create(vals_list)
        vals_list = [
            _flag_manual_line(_drop_stale_amount_currency(vals))
            if vals.get('move_id') in manual.ids else vals
            for vals in vals_list
        ]
        for vals in vals_list:
            if vals.get('move_id') in manual.ids:
                trace.record(self.env, 'create', [vals['move_id']], vals)
        if len(manual) == len(moves) and all(vals.get('move_id') for vals in vals_list):
            return super(AccountMoveLine, self.with_context(**MANUAL_CONTEXT)).create(vals_list)
        lines = self.browse()
        for vals in vals_list:
            ctx = MANUAL_CONTEXT if vals.get('move_id') in manual.ids else {}
            lines |= super(AccountMoveLine, self.with_context(**ctx)).create([vals])
        return lines

    def write(self, vals):
        manual = self.filtered(lambda l: l.move_id.manual_journal_items)
        if not manual:
            return super().write(vals)
        vals = _drop_stale_amount_currency(vals)
        trace.record(self.env, 'write', manual.ids, vals)
        res = super(AccountMoveLine, manual.with_context(**MANUAL_CONTEXT)).write(vals)
        rest = self - manual
        if rest:
            res = super(AccountMoveLine, rest).write(vals)
        return res

    def unlink(self):
        manual = self.filtered(lambda l: l.move_id.manual_journal_items)
        if manual:
            trace.record(self.env, 'unlink', manual.ids)
        return super().unlink()
