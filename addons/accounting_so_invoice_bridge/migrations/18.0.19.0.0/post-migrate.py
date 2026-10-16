def migrate(cr, version):
    """A stock request used to hold ONE product (product_id + quantity on
    the request). It now has product lines: move the old product into a
    line, then drop the old columns."""
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'sale_stock_request'
           AND column_name IN ('product_id', 'quantity')
    """)
    columns = {row[0] for row in cr.fetchall()}
    if columns != {'product_id', 'quantity'}:
        return
    cr.execute("""
        INSERT INTO sale_stock_request_line
               (request_id, product_id, quantity,
                create_uid, create_date, write_uid, write_date)
        SELECT r.id, r.product_id, r.quantity,
               r.create_uid, r.create_date, r.write_uid, r.write_date
          FROM sale_stock_request r
         WHERE r.product_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM sale_stock_request_line l
                            WHERE l.request_id = r.id)
    """)
    cr.execute("ALTER TABLE sale_stock_request DROP COLUMN product_id")
    cr.execute("ALTER TABLE sale_stock_request DROP COLUMN quantity")
