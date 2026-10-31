from odoo import fields, models, tools

AGEING_BUCKETS = [
    ('not_due', 'Not Due'),
    ('1_30', '1-30 Days'),
    ('31_60', '31-60 Days'),
    ('61_90', '61-90 Days'),
    ('90_plus', '90+ Days'),
    ('paid', 'Paid'),
]

# One row per posted CREDIT customer invoice / credit note, in company
# currency (the *_signed amounts: credit notes are negative). "Today" is the
# database's CURRENT_DATE at the moment the report is read, so overdue days
# and ageing are always current without any recomputation.
#
# Shared with customer.credit.summary (which aggregates the same rows), so
# both reports can never disagree.
_CREDIT_LINE_BASE = """
    SELECT
        am.id                                   AS id,
        am.id                                   AS move_id,
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
                                                AS amount_overdue
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
    partner_id = fields.Many2one('res.partner', string='Customer',
                                 readonly=True)
    invoice_partner_id = fields.Many2one('res.partner', string='Invoiced To',
                                         readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson',
                              readonly=True)
    move_type = fields.Selection([('out_invoice', 'Invoice'),
                                  ('out_refund', 'Credit Note')],
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

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"CREATE OR REPLACE VIEW {self._table} AS ({CREDIT_LINE_SELECT})")

    def action_open_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
