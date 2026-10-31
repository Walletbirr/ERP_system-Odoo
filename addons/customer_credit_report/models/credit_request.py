from odoo import _, api, fields, models

from .credit_line import AGEING_BUCKETS

REQUEST_STATES = [
    ('pending', 'Waiting for Manager'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Replaced / Cancelled'),
]


class CustomerCreditRequest(models.Model):
    """Credit Sales Report.

    Created when the salesperson sends a credit quotation to the
    High-Level Manager. It freezes the customer's credit position at that
    moment (what they owe, what is overdue, how old it is, their open
    invoices) next to the new sale, so the manager decides on facts and
    the decision can be audited later even after payments change the
    live figures.
    """
    _name = 'customer.credit.request'
    _description = 'Credit Sales Report'
    _inherit = ['mail.thread']
    _order = 'request_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False,
                       readonly=True, default=lambda self: _('New'))
    state = fields.Selection(REQUEST_STATES, default='pending',
                             required=True, readonly=True, tracking=True,
                             index=True)
    sale_order_id = fields.Many2one('sale.order', string='Sales Order',
                                    required=True, readonly=True,
                                    ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Customer',
                                 required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', required=True,
                                 readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True,
                                  help='Company currency.')
    user_id = fields.Many2one('res.users', string='Salesperson',
                              readonly=True)
    requested_by_id = fields.Many2one('res.users', string='Sent By',
                                      readonly=True)
    request_date = fields.Datetime(string='Sent On', readonly=True)
    note = fields.Text(string="Salesperson's Note", readonly=True)

    # The new sale
    order_currency_id = fields.Many2one('res.currency', readonly=True)
    order_amount = fields.Monetary(string='This Sale',
                                   currency_field='order_currency_id',
                                   readonly=True)
    order_amount_company = fields.Monetary(
        string='This Sale (company currency)', readonly=True)
    payment_term_id = fields.Many2one('account.payment.term',
                                      string='Sales Type', readonly=True)
    branch_name = fields.Char(string='Branch', readonly=True)
    order_line_ids = fields.One2many(related='sale_order_id.order_line',
                                     string='Products')

    # Customer position when the report was sent
    credit_total = fields.Monetary(string='Total Credit Taken',
                                   readonly=True)
    credit_paid = fields.Monetary(string='Paid', readonly=True)
    credit_remaining = fields.Monetary(string='Owes Now', readonly=True)
    credit_overdue = fields.Monetary(string='Of Which Overdue',
                                     readonly=True)
    credit_after = fields.Monetary(
        string='Will Owe After This Sale', readonly=True,
        help='Owes Now + This Sale.')
    invoice_count = fields.Integer(string='Credit Invoices So Far',
                                   readonly=True)
    open_invoice_count = fields.Integer(string='Open Credit Invoices',
                                        readonly=True)
    amount_not_due = fields.Monetary(string='Not Due', readonly=True)
    amount_1_30 = fields.Monetary(string='1-30 Days', readonly=True)
    amount_31_60 = fields.Monetary(string='31-60 Days', readonly=True)
    amount_61_90 = fields.Monetary(string='61-90 Days', readonly=True)
    amount_90_plus = fields.Monetary(string='90+ Days', readonly=True)
    max_days_overdue = fields.Integer(string='Oldest Overdue (days)',
                                      readonly=True)
    oldest_due_date = fields.Date(readonly=True)
    first_invoice_date = fields.Date(string='On Credit Since',
                                     readonly=True)
    last_payment_date = fields.Date(string='Last Payment', readonly=True)
    amount_unapplied = fields.Monetary(string='Unmatched Payments',
                                       readonly=True)
    paid_ratio = fields.Float(
        string='Paid %', readonly=True, aggregator='avg',
        help='Share of all credit ever taken that is already paid '
             '(0.25 = 25 %).')
    is_new_customer = fields.Boolean(
        string='First Credit Sale', readonly=True,
        help='The customer never bought on credit before.')
    line_ids = fields.One2many('customer.credit.request.line', 'request_id',
                               string='Open Credit Invoices',
                               readonly=True)

    # Decision
    decided_by_id = fields.Many2one('res.users', string='Decided By',
                                    readonly=True)
    decision_date = fields.Datetime(readonly=True)
    decision_note = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = seq.next_by_code(
                    'customer.credit.request') or _('New')
        return super().create(vals_list)

    @api.model
    def _create_for_order(self, order):
        company = order.company_id
        partner = order.partner_id.commercial_partner_id
        Summary = self.env['customer.credit.summary'].sudo()
        pos = Summary._position(partner, company)
        amount_company = order.currency_id._convert(
            order.amount_total, company.currency_id, company,
            fields.Date.context_today(self))
        self.env['customer.credit.line'].invalidate_model()
        open_lines = self.env['customer.credit.line'].sudo().search([
            ('partner_id', '=', partner.id),
            ('company_id', '=', company.id),
            ('is_open', '=', True),
        ], order='date_due asc, id asc')
        branch = getattr(order, 'sale_branch_id', False)
        vals = {
            'sale_order_id': order.id,
            'partner_id': partner.id,
            'company_id': company.id,
            'currency_id': company.currency_id.id,
            'user_id': order.user_id.id,
            'requested_by_id': self.env.user.id,
            'request_date': fields.Datetime.now(),
            'note': order.x_credit_note,
            'order_currency_id': order.currency_id.id,
            'order_amount': order.amount_total,
            'order_amount_company': amount_company,
            'payment_term_id': order.payment_term_id.id,
            'branch_name': branch.display_name if branch else False,
            'credit_total': pos['amount_total'],
            'credit_paid': pos['amount_paid'],
            'credit_remaining': pos['remaining'],
            'credit_overdue': pos['overdue'],
            'credit_after': pos['remaining'] + amount_company,
            'invoice_count': pos['invoice_count'],
            'open_invoice_count': pos['open_invoice_count'],
            'amount_not_due': pos['not_due'],
            'amount_1_30': pos['d1_30'],
            'amount_31_60': pos['d31_60'],
            'amount_61_90': pos['d61_90'],
            'amount_90_plus': pos['d90_plus'],
            'max_days_overdue': pos['max_days_overdue'],
            'oldest_due_date': pos['oldest_due_date'],
            'first_invoice_date': pos['first_invoice_date'],
            'last_payment_date': pos['last_payment_date'],
            'amount_unapplied': pos['unapplied'],
            'paid_ratio': (pos['amount_paid'] / pos['amount_total']
                           if pos['amount_total'] > 0 else 0.0),
            'is_new_customer': not pos['invoice_count'],
            'line_ids': [(0, 0, {
                'move_id': line.move_id.id,
                'invoice_name': line.move_id.name,
                'move_type': line.move_type,
                'invoice_date': line.invoice_date,
                'date_due': line.date_due,
                'origin': line.origin,
                'amount_total': line.amount_total,
                'amount_residual': line.amount_residual,
                'days_overdue': line.days_overdue,
                'ageing': line.ageing,
            }) for line in open_lines],
        }
        return self.create(vals)

    def _set_decision(self, decision, note=None):
        """decision: 'approved' / 'rejected'. Called from the order's
        manager decision."""
        pending = self.filtered(lambda r: r.state == 'pending')
        pending.write({
            'state': decision,
            'decided_by_id': self.env.user.id,
            'decision_date': fields.Datetime.now(),
            'decision_note': note or False,
        })
        return pending

    def action_open_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_view_customer_credit(self):
        self.ensure_one()
        return self.partner_id.action_view_credit_lines()

    def action_open_statement(self):
        self.ensure_one()
        return self.partner_id.action_open_credit_statement()

    def action_print(self):
        return self.env.ref(
            'customer_credit_report.action_report_credit_request'
        ).report_action(self)


class CustomerCreditRequestLine(models.Model):
    _name = 'customer.credit.request.line'
    _description = 'Credit Sales Report - Open Invoice'
    _order = 'date_due asc, id asc'

    request_id = fields.Many2one('customer.credit.request', required=True,
                                 ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='request_id.currency_id')
    move_id = fields.Many2one('account.move', string='Invoice')
    invoice_name = fields.Char(string='Invoice')
    move_type = fields.Selection([('out_invoice', 'Invoice'),
                                  ('out_refund', 'Credit Note')],
                                 string='Type')
    invoice_date = fields.Date()
    date_due = fields.Date(string='Due Date')
    origin = fields.Char(string='Sales Order')
    amount_total = fields.Monetary(string='Amount')
    amount_residual = fields.Monetary(string='Unpaid')
    days_overdue = fields.Integer()
    ageing = fields.Selection(AGEING_BUCKETS)
