from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """ Tick Exclude on existing DRAFT lines that use a bank / cash account
    (the second bank of a split payment). Posted payments are not touched. """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env['account.payment.multi.line']
    accounts = Line._get_liquidity_accounts()
    if not accounts:
        return
    lines = Line.search([
        ('account_id', 'in', accounts.ids),
        ('payment_id.state', '=', 'draft'),
        ('exclude_from_amount', '=', False),
    ])
    if lines:
        lines.write({'exclude_from_amount': True})
        lines.mapped('payment_id')._sync_multi_line_amount()
