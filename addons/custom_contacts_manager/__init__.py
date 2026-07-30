from . import models
from . import wizards


def pre_init_hook(env):
    """If a previous install attempt crashed partway through (common while
    iterating on a module), the default category rows (code='internal',
    'client', etc.) can be left behind in the database without their
    corresponding external-id link, causing a duplicate-key error the next
    time this module tries to (re)create them. This clears out only those
    orphaned rows - never touches ones already properly tracked - so a
    fresh install/upgrade attempt can proceed cleanly."""
    cr = env.cr
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'res_partner_classification'
        )
    """)
    if not cr.fetchone()[0]:
        return  # fresh install, table doesn't exist yet - nothing to clean

    cr.execute("""
        DELETE FROM res_partner_classification
        WHERE code IN ('internal', 'client', 'customer', 'vendor', 'company')
          AND id NOT IN (
              SELECT res_id FROM ir_model_data
              WHERE model = 'res.partner.classification'
          )
    """)
