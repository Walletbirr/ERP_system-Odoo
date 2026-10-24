def migrate(cr, version):
    """The High-Level Manager now approves AFTER Accounting approved the
    payment proof, and the invoice stays locked until then.

    Orders that already have an invoice went through the old flow (no
    manager step): mark them approved so nothing about them changes.
    Orders with an approved proof but no invoice yet are deliberately left
    alone: they now show a "Send to Manager" button, so the manager decides
    on them like on any new order.
    """
    cr.execute("""
        UPDATE sale_order so
           SET approval_state = 'approved'
         WHERE COALESCE(so.approval_state, 'not_required') = 'not_required'
           AND EXISTS (
                SELECT 1
                  FROM account_move_line aml
                  JOIN sale_order_line_invoice_rel rel
                    ON rel.invoice_line_id = aml.id
                  JOIN sale_order_line sol
                    ON sol.id = rel.order_line_id
                 WHERE sol.order_id = so.id)
    """)
