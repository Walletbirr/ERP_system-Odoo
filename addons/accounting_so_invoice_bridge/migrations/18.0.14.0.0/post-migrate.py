def migrate(cr, version):
    """Manager approval is no longer part of the Sales flow: stop flagging
    open quotations that have not entered an approval yet. Orders that are
    currently 'Pending Approval' are left alone so the manager can still
    finish them."""
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'sale_order'
           AND column_name IN ('requires_credit_approval', 'approval_state')
        HAVING count(*) = 2
    """)
    if cr.fetchone():
        cr.execute("""
            UPDATE sale_order
               SET requires_credit_approval = false
             WHERE state IN ('draft', 'sent')
               AND COALESCE(approval_state, 'not_required')
                   IN ('not_required', 'rejected')
        """)
