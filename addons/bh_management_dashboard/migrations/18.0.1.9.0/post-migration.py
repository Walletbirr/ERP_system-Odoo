# -*- coding: utf-8 -*-
"""Owner Withdrawal and Owner Fund now share ONE account list
(owner_account_ids). Carry over whatever was selected in the two old lists
so the Company > Finance screens keep working without re-configuring."""


def _table_exists(cr, name):
    cr.execute("SELECT to_regclass(%s)", (name,))
    return cr.fetchone()[0] is not None


def migrate(cr, version):
    if not version or not _table_exists(cr, 'bh_dash_cfg_owner_rel'):
        return
    for old in ('bh_dash_cfg_withdraw_rel', 'bh_dash_cfg_ownerfund_rel'):
        if _table_exists(cr, old):
            cr.execute("""
                INSERT INTO bh_dash_cfg_owner_rel (config_id, account_id)
                SELECT config_id, account_id FROM %s
                ON CONFLICT DO NOTHING
            """ % old)
