from odoo import _, fields, models, tools

from .credit_line import CREDIT_LINE_SELECT


class CustomerCreditSummary(models.Model):
    """One row per customer (company level) and company: everything the
    customer was given on credit, what was paid, what remains and how old
    it is. Aggregates exactly the rows of customer.credit.line."""
    _name = 'customer.credit.summary'
    _description = 'Customer Credit Summary'
    _auto = False
    _rec_name = 'partner_id'
    _order = 'amount_residual desc, partner_id'

    partner_id = fields.Many2one('res.partner', string='Customer',
                                 readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson',
                              readonly=True,
                              help="The customer's salesperson (contact).")
    invoice_count = fields.Integer(string='Credit Invoices', readonly=True)
    open_invoice_count = fields.Integer(string='Open Invoices',
                                        readonly=True)
    amount_total = fields.Monetary(string='Total Credit', readonly=True)
    amount_paid = fields.Monetary(string='Paid', readonly=True)
    amount_residual = fields.Monetary(string='Remaining', readonly=True)
    amount_overdue = fields.Monetary(string='Overdue', readonly=True)
    amount_not_due = fields.Monetary(string='Not Due', readonly=True)
    amount_1_30 = fields.Monetary(string='1-30', readonly=True)
    amount_31_60 = fields.Monetary(string='31-60', readonly=True)
    amount_61_90 = fields.Monetary(string='61-90', readonly=True)
    amount_90_plus = fields.Monetary(string='90+', readonly=True)
    max_days_overdue = fields.Integer(string='Oldest Overdue (days)',
                                      readonly=True)
    oldest_due_date = fields.Date(string='Oldest Due Date', readonly=True,
                                  help='Earliest due date still unpaid.')
    first_invoice_date = fields.Date(string='Customer on Credit Since',
                                     readonly=True)
    last_invoice_date = fields.Date(string='Last Credit Invoice',
                                    readonly=True)
    last_payment_date = fields.Date(string='Last Payment', readonly=True)
    amount_unapplied = fields.Monetary(
        string='Unmatched Payments', readonly=True,
        help="Money received from this customer that is not matched to "
             "any invoice yet (Accounting should match it with the "
             "invoice's Pay / Outstanding credits). Not deducted from "
             "Remaining.")

    # Customer history (form view tabs)
    open_line_ids = fields.Many2many(
        'customer.credit.line', string='Open Invoices',
        compute='_compute_history')
    line_ids = fields.Many2many(
        'customer.credit.line', string='All Credit Invoices',
        compute='_compute_history')
    settlement_ids = fields.Many2many(
        'customer.credit.settlement', string='Payment Settlements',
        compute='_compute_history')
    request_ids = fields.Many2many(
        'customer.credit.request', string='Credit Sales Reports',
        compute='_compute_history')

    def _compute_history(self):
        self.env.flush_all()
        for model in ('customer.credit.line', 'customer.credit.settlement'):
            self.env[model].invalidate_model()
        Line = self.env['customer.credit.line']
        Settlement = self.env['customer.credit.settlement']
        Request = self.env['customer.credit.request']
        for rec in self:
            dom = [('partner_id', '=', rec.partner_id.id),
                   ('company_id', '=', rec.company_id.id)]
            lines = Line.search(dom, order='invoice_date desc, id desc')
            rec.line_ids = lines
            rec.open_line_ids = lines.filtered('is_open').sorted(
                lambda l: (l.date_due or l.invoice_date, l.id))
            rec.settlement_ids = Settlement.search(dom)
            rec.request_ids = Request.search(dom)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # id: partner * 100 + company keeps one stable row per customer
        # and company (fewer than 100 companies).
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    l.partner_id * 100 + l.company_id      AS id,
                    l.partner_id                           AS partner_id,
                    l.company_id                           AS company_id,
                    MIN(l.currency_id)                     AS currency_id,
                    MIN(rp.user_id)                        AS user_id,
                    COUNT(*) FILTER (
                        WHERE l.move_type = 'out_invoice')  AS invoice_count,
                    COUNT(*) FILTER (
                        WHERE l.move_type = 'out_invoice'
                          AND l.is_open)                   AS open_invoice_count,
                    SUM(l.amount_total)                    AS amount_total,
                    SUM(l.amount_paid)                     AS amount_paid,
                    SUM(l.amount_residual)                 AS amount_residual,
                    SUM(l.amount_overdue)                  AS amount_overdue,
                    SUM(l.amount_not_due)                  AS amount_not_due,
                    SUM(l.amount_1_30)                     AS amount_1_30,
                    SUM(l.amount_31_60)                    AS amount_31_60,
                    SUM(l.amount_61_90)                    AS amount_61_90,
                    SUM(l.amount_90_plus)                  AS amount_90_plus,
                    MAX(l.days_overdue)                    AS max_days_overdue,
                    MIN(l.date_due) FILTER (
                        WHERE l.amount_residual > 0.005)   AS oldest_due_date,
                    MIN(l.invoice_date)                    AS first_invoice_date,
                    MAX(l.invoice_date)                    AS last_invoice_date,
                    MAX(l.last_payment_date)               AS last_payment_date,
                    COALESCE(MAX(un.amount), 0)            AS amount_unapplied
                FROM ({CREDIT_LINE_SELECT}) l
                JOIN res_partner rp ON rp.id = l.partner_id
                LEFT JOIN LATERAL (
                    -- receivable credit lines (payments) not fully matched
                    SELECT -SUM(aml.amount_residual) AS amount
                      FROM account_move_line aml
                      JOIN account_account aa ON aa.id = aml.account_id
                      JOIN res_partner p ON p.id = aml.partner_id
                     WHERE aa.account_type = 'asset_receivable'
                       AND aml.parent_state = 'posted'
                       AND aml.amount_residual < -0.005
                       AND aml.company_id = l.company_id
                       AND COALESCE(p.commercial_partner_id, p.id)
                           = l.partner_id
                ) un ON TRUE
                GROUP BY l.partner_id, l.company_id
            )
        """)

    # ------------------------------------------------------------------
    # Helpers used by sale.order, res.partner and the credit request
    # ------------------------------------------------------------------
    @staticmethod
    def _empty_position():
        return {
            'amount_total': 0.0, 'amount_paid': 0.0, 'remaining': 0.0,
            'overdue': 0.0, 'invoice_count': 0, 'open_invoice_count': 0,
            'not_due': 0.0, 'd1_30': 0.0, 'd31_60': 0.0, 'd61_90': 0.0,
            'd90_plus': 0.0, 'max_days_overdue': 0, 'oldest_due_date': False,
            'first_invoice_date': False, 'last_payment_date': False,
            'unapplied': 0.0,
        }

    def _position(self, partner, company):
        """The customer's credit position (dict) right now."""
        # The view reads invoices/payments in SQL: write pending ORM
        # changes first (e.g. a payment registered in the same request).
        self.env.flush_all()
        self.invalidate_model()
        row = self.search([
            ('partner_id', '=', partner.commercial_partner_id.id),
            ('company_id', '=', company.id),
        ], limit=1)
        if not row:
            return self._empty_position()
        return {
            'amount_total': row.amount_total,
            'amount_paid': row.amount_paid,
            'remaining': row.amount_residual,
            'overdue': row.amount_overdue,
            'invoice_count': row.invoice_count,
            'open_invoice_count': row.open_invoice_count,
            'not_due': row.amount_not_due,
            'd1_30': row.amount_1_30,
            'd31_60': row.amount_31_60,
            'd61_90': row.amount_61_90,
            'd90_plus': row.amount_90_plus,
            'max_days_overdue': row.max_days_overdue,
            'oldest_due_date': row.oldest_due_date,
            'first_invoice_date': row.first_invoice_date,
            'last_payment_date': row.last_payment_date,
            'unapplied': row.amount_unapplied,
        }

    def action_view_lines(self):
        self.ensure_one()
        return self.partner_id.action_view_credit_lines()

    def action_view_settlements(self):
        self.ensure_one()
        return self.partner_id.action_view_credit_settlements()

    def action_open_statement(self):
        self.ensure_one()
        return self.partner_id.action_open_credit_statement()

    def action_new_credit_payment(self):
        """The customer paid: record it with the slip for Accounting."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credit Payment'),
            'res_model': 'customer.credit.payment',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'context': {'default_partner_id': self.partner_id.id,
                        'default_company_id': self.company_id.id},
        }
