def migrate(cr, version):
    """Credit sales now need the High-Level Manager before confirmation.

    Open quotations get requires_credit_approval from their Sale Type
    (customer_credit_report). Confirmed orders are left exactly as they
    are.
    """
    if not version:
        return
    cr.execute("""
        UPDATE sale_order
           SET requires_credit_approval = (x_sale_type = 'credit')
         WHERE state IN ('draft', 'sent')
           AND approval_state IN ('not_required', 'rejected')
    """)
