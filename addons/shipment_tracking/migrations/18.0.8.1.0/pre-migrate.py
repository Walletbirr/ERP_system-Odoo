# /custom_addons/shipment_tracking/migrations/18.0.8.1.0/pre-migrate.py
#
# port_of_loading / port_of_discharge are changing from Char (text) to
# Many2one (integer FK) on shipment.tracking. If we let Odoo's normal
# _auto_init column-type conversion handle this, it runs:
#   ALTER TABLE shipment_tracking ALTER COLUMN port_of_loading TYPE integer
# which fails with "invalid input syntax for type integer" for any
# existing free-text value (e.g. "Chiba", "Shanghai, China").
#
# Fix: rename the old text columns aside BEFORE the ORM sees them. With
# the original column name gone, the ORM just ADDs a fresh empty integer
# column instead of trying to convert one. post-migrate.py then creates
# shipment.location records from the saved text values and repopulates
# the new integer columns to point at them.

from odoo.tools.sql import column_exists, table_exists

_COLUMNS = {
    'port_of_loading': 'x_migrate_port_of_loading_text',
    'port_of_discharge': 'x_migrate_port_of_discharge_text',
}


def migrate(cr, version):
    if not table_exists(cr, 'shipment_tracking'):
        return

    for col, tmp_col in _COLUMNS.items():
        if not column_exists(cr, 'shipment_tracking', col):
            continue
        if column_exists(cr, 'shipment_tracking', tmp_col):
            # Already renamed by a previous (partial) upgrade attempt
            continue

        cr.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'shipment_tracking' AND column_name = %s",
            (col,),
        )
        row = cr.fetchone()
        data_type = row[0] if row else None

        if data_type in ('integer', 'bigint'):
            # Already converted (e.g. this migration already ran once
            # successfully) — nothing to do.
            continue

        cr.execute(
            'ALTER TABLE shipment_tracking RENAME COLUMN "%s" TO "%s"' % (col, tmp_col)
        )
