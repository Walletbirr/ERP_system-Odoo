"""18.0.31.1.0: voids are final in one step (no Accounting verification).
Voids made with 18.0.31.0.0 that were still "To Verify" / "Sent Back" are
made final now (cancelled, numbered VOID/<paper no>); every void gets the
single status "Void"; their verification To-Dos are removed."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Move = env['account.move']
    voids = Move.search([('x_is_void', '=', True)])
    if not voids:
        return
    for move in voids.filtered(lambda m: m.state != 'cancel'):
        move.with_context(bridge_void_create=True).button_cancel()
        move.name = 'VOID/' + (move.cim_reference or '').strip()
    cr.execute("UPDATE account_move SET x_void_state = 'void' "
               "WHERE x_is_void")
    env['mail.activity'].search([
        ('res_model', '=', 'account.move'),
        ('res_id', 'in', voids.ids),
        ('summary', 'in', ('Verify void paper invoice',
                           'Void paper invoice sent back')),
    ]).unlink()
