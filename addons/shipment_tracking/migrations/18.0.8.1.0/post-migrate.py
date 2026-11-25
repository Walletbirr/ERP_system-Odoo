# /custom_addons/shipment_tracking/migrations/18.0.8.1.0/post-migrate.py
#
# Runs after the ORM has created the shipment.location table and the new
# (empty) integer port_of_loading / port_of_discharge columns on
# shipment_tracking (see pre-migrate.py). This script:
#   1. Creates one shipment.location record per distinct old text value.
#   2. Points the new integer columns at the matching location.
#   3. Drops the temporary text columns.

from odoo.tools.sql import column_exists, table_exists

_COLUMNS = {
    'port_of_loading': 'x_migrate_port_of_loading_text',
    'port_of_discharge': 'x_migrate_port_of_discharge_text',
}


def migrate(cr, version):
    if not table_exists(cr, 'shipment_tracking'):
        return
    if not table_exists(cr, 'shipment_location'):
        # Shouldn't happen — the module's own tables are created before
        # post-migrate runs — but bail out safely if it ever does.
        return

    for col, tmp_col in _COLUMNS.items():
        if not column_exists(cr, 'shipment_tracking', tmp_col):
            continue

        # 1. Create a shipment.location for every distinct non-empty
        #    old text value that doesn't already have one (case-sensitive,
        #    trimmed exact match — de-dupes "Chiba" vs " Chiba ").
        cr.execute("""
            INSERT INTO shipment_location (name, sequence, active, create_date, write_date)
            SELECT DISTINCT trim(t.{tmp_col}), 10, true, now(), now()
            FROM shipment_tracking t
            WHERE t.{tmp_col} IS NOT NULL
              AND trim(t.{tmp_col}) != ''
              AND NOT EXISTS (
                  SELECT 1 FROM shipment_location l
                  WHERE l.name = trim(t.{tmp_col})
              )
        """.format(tmp_col=tmp_col))

        # 2. Point the new integer FK column at the matching location.
        cr.execute("""
            UPDATE shipment_tracking t
            SET {col} = l.id
            FROM shipment_location l
            WHERE l.name = trim(t.{tmp_col})
              AND t.{tmp_col} IS NOT NULL
              AND trim(t.{tmp_col}) != ''
        """.format(col=col, tmp_col=tmp_col))

        # 3. Drop the now-unneeded temporary text column.
        cr.execute('ALTER TABLE shipment_tracking DROP COLUMN "%s"' % tmp_col)
