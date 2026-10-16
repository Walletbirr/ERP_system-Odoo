def migrate(cr, version):
    """Existing orders: the sales Branch (new) starts as the warehouse the
    order already delivers from, so old orders are not left blank in
    reports."""
    cr.execute("""
        UPDATE sale_order
           SET x_sale_branch_id = warehouse_id
         WHERE x_sale_branch_id IS NULL
           AND warehouse_id IS NOT NULL
    """)
