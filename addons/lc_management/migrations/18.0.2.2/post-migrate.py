from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Back-fill the PO payment rows for LCs already opened/settled."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    pos = env['purchase.order'].search([('lc_id', '!=', False)])
    pos._lc_sync_margin_payment()
    env['lc.settlement.line'].search([('state', '=', 'confirmed')])._sync_po_payment()
