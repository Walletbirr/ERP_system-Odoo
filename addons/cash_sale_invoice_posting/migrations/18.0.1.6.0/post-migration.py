import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Cash sale invoices posted with the receivable line on the customer's
    account were left open (Pay button, 'Not Paid'). A cash sale is paid by
    definition, so recompute the stored amounts and the payment status of
    every posted cash sale invoice."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    moves = env['account.move'].search([
        ('x_is_cash_sale', '=', True),
        ('move_type', '=', 'out_invoice'),
        ('state', '=', 'posted'),
    ])
    if not moves:
        return
    for name in ('amount_residual', 'amount_residual_signed', 'payment_state'):
        env.add_to_compute(moves._fields[name], moves)
    moves.flush_recordset()
    _logger.info("Recomputed payment status of %s posted cash sale invoices",
                 len(moves))
