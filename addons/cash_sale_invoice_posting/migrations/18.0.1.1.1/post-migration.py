import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """An abandoned earlier attempt (a "Cash Sale Receipt" smart button) can
    leave an account.move view that reads the field x_cash_receipt_count,
    which no longer exists. Opening any journal entry then fails with
    "Invalid field 'x_cash_receipt_count' on model 'account.move'".
    Deactivate such orphan views (no data is deleted)."""
    cr.execute("""
        SELECT v.id, v.name FROM ir_ui_view v
         WHERE v.model = 'account.move' AND v.active
           AND v.arch_db::text LIKE '%%x_cash_receipt_count%%'
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_fields f
                 WHERE f.model = 'account.move'
                   AND f.name = 'x_cash_receipt_count')
    """)
    rows = cr.fetchall()
    if rows:
        cr.execute("UPDATE ir_ui_view SET active = FALSE WHERE id IN %s",
                   (tuple(r[0] for r in rows),))
        _logger.warning("Deactivated orphan account.move views: %s", rows)
