"""Give existing orders and invoices their Cash / Credit sale type.

Used on a fresh install (post_init_hook) and when upgrading from the old
1.x module (migrations/18.0.2.0.0). Before this module there was no explicit
sale type: an order was treated as credit when its payment term's name
contains "credit" (accounting_so_invoice_bridge did the same), so that rule
is used once, here, to tick "Credit Sale" on those payment terms and to
classify the existing data. From now on the payment term chosen on the
quotation (labelled "Sales Type") decides: a term ticked Credit Sale makes a
Credit sale.
"""
import logging

_logger = logging.getLogger(__name__)

# Payment term names are translatable (jsonb); search every language.
_TERM_IS_CREDIT = """
    EXISTS (
        SELECT 1 FROM jsonb_each_text(apt.name) t
         WHERE t.value ILIKE '%%credit%%'
    )
"""


def flag_credit_payment_terms(cr):
    """Payment terms whose name says "credit" become Credit Sale terms."""
    cr.execute(f"""
        UPDATE account_payment_term apt
           SET x_is_credit = TRUE
         WHERE {_TERM_IS_CREDIT}
    """)
    return cr.rowcount


def set_initial_sale_types(cr):
    terms = flag_credit_payment_terms(cr)
    _logger.info("customer_credit_report: %s payment terms marked Credit "
                 "Sale.", terms)
    # Orders: credit when their payment term is a Credit Sale term.
    cr.execute("""
        UPDATE sale_order so
           SET x_sale_type = CASE WHEN apt.x_is_credit THEN 'credit'
                                  ELSE 'cash' END
          FROM account_payment_term apt
         WHERE so.payment_term_id = apt.id
    """)
    cr.execute("""
        UPDATE sale_order SET x_sale_type = 'cash'
         WHERE payment_term_id IS NULL
    """)
    cr.execute("SELECT count(*) FROM sale_order WHERE x_sale_type = 'credit'")
    orders = cr.fetchone()[0]

    # Invoices made from orders follow their orders (credit wins).
    cr.execute("""
        UPDATE account_move am
           SET x_sale_type = CASE WHEN EXISTS (
                   SELECT 1
                     FROM account_move_line aml
                     JOIN sale_order_line_invoice_rel rel
                       ON rel.invoice_line_id = aml.id
                     JOIN sale_order_line sol ON sol.id = rel.order_line_id
                     JOIN sale_order so ON so.id = sol.order_id
                    WHERE aml.move_id = am.id
                      AND so.x_sale_type = 'credit')
               THEN 'credit' ELSE 'cash' END
         WHERE am.move_type IN ('out_invoice', 'out_refund')
           AND EXISTS (
                   SELECT 1
                     FROM account_move_line aml
                     JOIN sale_order_line_invoice_rel rel
                       ON rel.invoice_line_id = aml.id
                    WHERE aml.move_id = am.id)
    """)
    # Invoices without an order: by their own payment term.
    cr.execute("""
        UPDATE account_move am
           SET x_sale_type = 'credit'
          FROM account_payment_term apt
         WHERE am.invoice_payment_term_id = apt.id
           AND apt.x_is_credit
           AND am.move_type IN ('out_invoice', 'out_refund')
           AND NOT EXISTS (
                   SELECT 1
                     FROM account_move_line aml
                     JOIN sale_order_line_invoice_rel rel
                       ON rel.invoice_line_id = aml.id
                    WHERE aml.move_id = am.id)
    """)
    cr.execute("""
        UPDATE account_move SET x_sale_type = 'cash'
         WHERE move_type IN ('out_invoice', 'out_refund')
           AND x_sale_type IS NULL
    """)
    # Credit notes follow the invoice they reverse.
    cr.execute("""
        UPDATE account_move rf
           SET x_sale_type = inv.x_sale_type
          FROM account_move inv
         WHERE rf.reversed_entry_id = inv.id
           AND rf.move_type = 'out_refund'
           AND inv.x_sale_type IS NOT NULL
    """)
    _logger.info("customer_credit_report: %s existing orders are Credit "
                 "sales.", orders)


def post_init_hook(env):
    set_initial_sale_types(env.cr)
    env['account.payment.term'].invalidate_model(['x_is_credit'])
    env['account.move'].invalidate_model(['x_sale_type'])
    env['sale.order'].invalidate_model(['x_sale_type'])
