from odoo import fields, models, tools

AGEING_BUCKETS = [
    ('not_due', 'Not Due'),
    ('1_30', '1-30 Days'),
    ('31_60', '31-60 Days'),
    ('61_90', '61-90 Days'),
    ('90_plus', '90+ Days'),
    ('previous', 'Previous Balance'),
    ('paid', 'Paid'),
]

# Synthetic row ids of the previous balance (never collide with move ids).
PREVIOUS_ID_BASE = 10_000_000_000

# Customers who have their own account (contact field "Credit Account",
# company dependent, stored as jsonb {company_id: account_id}): what they
# owed before their first credit sale in Odoo is the PREVIOUS BALANCE.
#
#   boundary   = date of their first posted credit invoice on that account
#                (none yet: everything on the account is previous)
#   prev_start = what is on the account up to and including that date,
#                credit invoices / credit notes excluded (an old balance
#                entered the same day as the first sale still counts)
#   prev_now   = account balance now - what is still unpaid on the credit
#                invoices / credit notes posted on that account
#
# So the customer's total (previous balance + open credit invoices) is
# always the balance of their account. Nothing is posted for it.
CREDIT_ACCOUNTS_SQL = """
    SELECT rp.id                                         AS partner_id,
           c.id                                          AS company_id,
           (rp.x_credit_account_id ->> c.id::text)::int  AS account_id
      FROM res_partner rp
      JOIN res_company c
        ON rp.x_credit_account_id ? c.id::text
     WHERE rp.x_credit_account_id IS NOT NULL
       AND (rp.x_credit_account_id ->> c.id::text) IS NOT NULL
"""

# Part of a line of the Credit Account that is NOT about a credit invoice /
# credit note in Odoo: its balance, minus what of it is matched to one (a
# payment matched to a credit invoice is a payment of that sale, not of
# the previous balance). Used for the previous balance and the statement.
ACCOUNT_LINE_FREE_SQL = """
    (aml.balance
     + COALESCE((SELECT SUM(apr.amount)
                   FROM account_partial_reconcile apr
                   JOIN account_move_line d ON d.id = apr.debit_move_id
                   JOIN account_move dm ON dm.id = d.move_id
                  WHERE apr.credit_move_id = aml.id
                    AND dm.state = 'posted'
                    AND dm.move_type IN ('out_invoice', 'out_refund')
                    AND dm.x_sale_type = 'credit'), 0)
     - COALESCE((SELECT SUM(apr.amount)
                   FROM account_partial_reconcile apr
                   JOIN account_move_line c ON c.id = apr.credit_move_id
                   JOIN account_move cm ON cm.id = c.move_id
                  WHERE apr.debit_move_id = aml.id
                    AND cm.state = 'posted'
                    AND cm.move_type IN ('out_invoice', 'out_refund')
                    AND cm.x_sale_type = 'credit'), 0))
"""

# Lines of the Credit Account that do not belong to a credit invoice /
# credit note in Odoo (old balances, payments, adjustments...).
ACCOUNT_LINE_NOT_DOC_SQL = """
    NOT EXISTS (SELECT 1 FROM account_move m
                 WHERE m.id = aml.move_id
                   AND m.move_type IN ('out_invoice', 'out_refund')
                   AND m.x_sale_type = 'credit')
"""

def ensure_credit_account_column(cr):
    """The SQL views read res_partner.x_credit_account_id; make sure the
    column exists even if the views are created before res.partner is
    set up (install / upgrade order)."""
    cr.execute("ALTER TABLE res_partner "
               "ADD COLUMN IF NOT EXISTS x_credit_account_id jsonb")


PREVIOUS_BALANCE_SQL = f"""
    SELECT ca.partner_id, ca.company_id, ca.account_id,
           bd.boundary,
           st.last_date                                  AS prev_date,
           COALESCE(st.amount, 0)                        AS prev_start,
           COALESCE(nw.amount, 0) - COALESCE(dc.amount, 0)
                                                         AS prev_now,
           lp.last_payment_date
      FROM ({CREDIT_ACCOUNTS_SQL}) ca
      LEFT JOIN LATERAL (
          SELECT MIN(m.invoice_date) AS boundary
            FROM account_move m
           WHERE m.move_type = 'out_invoice'
             AND m.state = 'posted'
             AND m.x_sale_type = 'credit'
             AND m.company_id = ca.company_id
             AND EXISTS (SELECT 1 FROM account_move_line x
                          WHERE x.move_id = m.id
                            AND x.account_id = ca.account_id)
      ) bd ON TRUE
      LEFT JOIN LATERAL (
          SELECT SUM({ACCOUNT_LINE_FREE_SQL}) AS amount,
                 MAX(aml.date) AS last_date
            FROM account_move_line aml
           WHERE aml.account_id = ca.account_id
             AND aml.company_id = ca.company_id
             AND aml.parent_state = 'posted'
             AND {ACCOUNT_LINE_NOT_DOC_SQL}
             AND (bd.boundary IS NULL OR aml.date <= bd.boundary)
      ) st ON TRUE
      LEFT JOIN LATERAL (
          SELECT SUM(aml.balance) AS amount
            FROM account_move_line aml
           WHERE aml.account_id = ca.account_id
             AND aml.company_id = ca.company_id
             AND aml.parent_state = 'posted'
      ) nw ON TRUE
      LEFT JOIN LATERAL (
          SELECT SUM(aml.amount_residual) AS amount
            FROM account_move_line aml
            JOIN account_move m ON m.id = aml.move_id
           WHERE aml.account_id = ca.account_id
             AND aml.company_id = ca.company_id
             AND m.state = 'posted'
             AND m.move_type IN ('out_invoice', 'out_refund')
             AND m.x_sale_type = 'credit'
      ) dc ON TRUE
      LEFT JOIN LATERAL (
          SELECT MAX(aml.date) AS last_payment_date
            FROM account_move_line aml
            JOIN account_payment p ON p.move_id = aml.move_id
           WHERE aml.account_id = ca.account_id
             AND aml.company_id = ca.company_id
             AND aml.parent_state = 'posted'
             AND aml.balance < 0
      ) lp ON TRUE
"""

# One row per posted CREDIT customer invoice / credit note, in company
# currency (the *_signed amounts: credit notes are negative). "Today" is the
# database's CURRENT_DATE at the moment the report is read, so overdue days
# and ageing are always current without any recomputation.
#
# Shared with customer.credit.summary (which aggregates the same rows), so
# both reports can never disagree.
_CREDIT_LINE_BASE = f"""
    SELECT
        am.id::bigint                           AS id,
        am.id                                   AS move_id,
        am.name                                 AS name,
        am.commercial_partner_id                AS partner_id,
        am.partner_id                           AS invoice_partner_id,
        am.company_id                           AS company_id,
        rc.currency_id                          AS currency_id,
        am.invoice_user_id                      AS user_id,
        am.move_type                            AS move_type,
        am.invoice_date                         AS invoice_date,
        am.invoice_date_due                     AS date_due,
        am.invoice_origin                       AS origin,
        am.payment_state                        AS payment_state,
        am.amount_total_signed                  AS amount_total,
        am.amount_total_signed
            - am.amount_residual_signed         AS amount_paid,
        am.amount_residual_signed               AS amount_residual,
        ABS(am.amount_residual_signed) > 0.005  AS is_open,
        CASE WHEN am.amount_residual_signed > 0.005
                  AND am.invoice_date_due < CURRENT_DATE
             THEN CURRENT_DATE - am.invoice_date_due
             ELSE 0 END                         AS days_overdue,
        CASE WHEN ABS(am.amount_residual_signed) <= 0.005 THEN 'paid'
             WHEN am.invoice_date_due IS NULL
                  OR am.invoice_date_due >= CURRENT_DATE THEN 'not_due'
             WHEN CURRENT_DATE - am.invoice_date_due <= 30 THEN '1_30'
             WHEN CURRENT_DATE - am.invoice_date_due <= 60 THEN '31_60'
             WHEN CURRENT_DATE - am.invoice_date_due <= 90 THEN '61_90'
             ELSE '90_plus' END                 AS ageing,
        pay.last_payment_date                   AS last_payment_date
    FROM account_move am
    JOIN res_company rc ON rc.id = am.company_id
    LEFT JOIN LATERAL (
        SELECT MAX(cl.date) AS last_payment_date
          FROM account_move_line dl
          JOIN account_partial_reconcile apr ON apr.debit_move_id = dl.id
          JOIN account_move_line cl ON cl.id = apr.credit_move_id
          JOIN account_move cm ON cm.id = cl.move_id
         WHERE dl.move_id = am.id
           AND cm.move_type NOT IN ('out_refund', 'out_invoice')
    ) pay ON TRUE
    WHERE am.move_type IN ('out_invoice', 'out_refund')
      AND am.state = 'posted'
      AND am.x_sale_type = 'credit'
    UNION ALL
    SELECT
        {PREVIOUS_ID_BASE}::bigint + pb.partner_id::bigint * 1000
            + pb.company_id                     AS id,
        NULL::int                               AS move_id,
        'Previous balance'::varchar             AS name,
        pb.partner_id                           AS partner_id,
        pb.partner_id                           AS invoice_partner_id,
        pb.company_id                           AS company_id,
        rc.currency_id                          AS currency_id,
        rp.user_id                              AS user_id,
        'previous'::varchar                     AS move_type,
        COALESCE(pb.prev_date, CURRENT_DATE)    AS invoice_date,
        NULL::date                              AS date_due,
        NULL::varchar                           AS origin,
        NULL::varchar                           AS payment_state,
        pb.prev_start                           AS amount_total,
        pb.prev_start - pb.prev_now             AS amount_paid,
        pb.prev_now                             AS amount_residual,
        ABS(pb.prev_now) > 0.005                AS is_open,
        0                                       AS days_overdue,
        CASE WHEN ABS(pb.prev_now) <= 0.005 THEN 'paid'
             ELSE 'previous' END                AS ageing,
        pb.last_payment_date                    AS last_payment_date
    FROM ({PREVIOUS_BALANCE_SQL}) pb
    JOIN res_company rc ON rc.id = pb.company_id
    JOIN res_partner rp ON rp.id = pb.partner_id
    WHERE ABS(pb.prev_start) > 0.005 OR ABS(pb.prev_now) > 0.005
"""

# Remaining amount per ageing bucket as real columns, so a list or pivot
# grouped by customer IS the ageing report (each column sums per group).
CREDIT_LINE_SELECT = f"""
    SELECT b.*,
        CASE WHEN b.ageing = 'not_due' THEN b.amount_residual ELSE 0 END
                                                AS amount_not_due,
        CASE WHEN b.ageing = '1_30'    THEN b.amount_residual ELSE 0 END
                                                AS amount_1_30,
        CASE WHEN b.ageing = '31_60'   THEN b.amount_residual ELSE 0 END
                                                AS amount_31_60,
        CASE WHEN b.ageing = '61_90'   THEN b.amount_residual ELSE 0 END
                                                AS amount_61_90,
        CASE WHEN b.ageing = '90_plus' THEN b.amount_residual ELSE 0 END
                                                AS amount_90_plus,
        CASE WHEN b.days_overdue > 0  THEN b.amount_residual ELSE 0 END
                                                AS amount_overdue,
        CASE WHEN b.move_type = 'previous' THEN b.amount_residual ELSE 0 END
                                                AS amount_previous
    FROM ({_CREDIT_LINE_BASE}) b
"""


class CustomerCreditLine(models.Model):
    """Credit invoices (read-only report, built from posted invoices)."""
    _name = 'customer.credit.line'
    _description = 'Customer Credit Line'
    _auto = False
    _rec_name = 'move_id'
    _order = 'date_due asc, id asc'

    move_id = fields.Many2one('account.move', string='Invoice', readonly=True)
    name = fields.Char(string='Invoice', readonly=True,
                       help="Invoice number, or \"Previous balance\" (what "
                            "the customer owed before their first credit "
                            "sale in Odoo).")
    partner_id = fields.Many2one('res.partner', string='Customer',
                                 readonly=True)
    invoice_partner_id = fields.Many2one('res.partner', string='Invoiced To',
                                         readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson',
                              readonly=True)
    move_type = fields.Selection([('out_invoice', 'Invoice'),
                                  ('out_refund', 'Credit Note'),
                                  ('previous', 'Previous Balance')],
                                 string='Type', readonly=True)
    invoice_date = fields.Date(readonly=True)
    date_due = fields.Date(string='Due Date', readonly=True)
    origin = fields.Char(string='Sales Order', readonly=True)
    payment_state = fields.Selection(
        selection=lambda self: self.env['account.move']._fields[
            'payment_state'].selection,
        readonly=True)
    amount_total = fields.Monetary(string='Credit Amount', readonly=True)
    amount_paid = fields.Monetary(string='Paid', readonly=True)
    amount_residual = fields.Monetary(string='Remaining', readonly=True)
    is_open = fields.Boolean(string='Open', readonly=True)
    days_overdue = fields.Integer(readonly=True)
    ageing = fields.Selection(AGEING_BUCKETS, readonly=True)
    last_payment_date = fields.Date(readonly=True)

    # Remaining amount per ageing bucket (see CREDIT_LINE_SELECT).
    amount_not_due = fields.Monetary(string='Not Due', readonly=True)
    amount_1_30 = fields.Monetary(string='1-30', readonly=True)
    amount_31_60 = fields.Monetary(string='31-60', readonly=True)
    amount_61_90 = fields.Monetary(string='61-90', readonly=True)
    amount_90_plus = fields.Monetary(string='90+', readonly=True)
    amount_overdue = fields.Monetary(string='Overdue', readonly=True)
    amount_previous = fields.Monetary(string='Previous Balance',
                                      readonly=True)

    def init(self):
        ensure_credit_account_column(self.env.cr)
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"CREATE OR REPLACE VIEW {self._table} AS ({CREDIT_LINE_SELECT})")

    def action_open_invoice(self):
        self.ensure_one()
        if not self.move_id:
            # Previous balance: the customer's own account.
            return self.partner_id.with_company(
                self.company_id).action_view_credit_account()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
