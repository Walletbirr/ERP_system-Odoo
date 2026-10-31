from odoo import _, api, fields, models

SALE_TYPES = [('cash', 'Cash'), ('credit', 'Credit')]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # The Sales Type the salesperson picks is the Payment Terms field
    # (labelled "Sales Type" on the quotation). A term ticked "Credit Sale"
    # makes the order a Credit sale. Stored, so reports and history do not
    # change if a term is re-ticked later.
    x_sale_type = fields.Selection(
        SALE_TYPES, string='Sale Type', index=True, tracking=True,
        compute='_compute_x_sale_type', store=True, readonly=True,
        precompute=True,
        help="Cash or Credit, from the Sales Type (payment term) chosen on "
             "the quotation. Credit: the customer pays later; the sale "
             "needs the High-Level Manager's approval before it is "
             "confirmed.")
    x_credit_note = fields.Text(
        string='Credit Request Note',
        help="Why this customer should get credit (agreed due date, "
             "terms...). Sent to the manager with the Credit Sales Report.")
    x_credit_request_ids = fields.One2many(
        'customer.credit.request', 'sale_order_id',
        string='Credit Sales Reports', readonly=True)
    x_credit_request_count = fields.Integer(
        compute='_compute_x_credit_request_count')

    # The customer's credit position right now (read-only information for
    # the salesperson and the manager on a credit quotation).
    x_company_currency_id = fields.Many2one(
        related='company_id.currency_id', string='Company Currency')
    x_customer_credit_remaining = fields.Monetary(
        string='Customer Owes', compute='_compute_x_customer_credit',
        currency_field='x_company_currency_id')
    x_customer_credit_overdue = fields.Monetary(
        string='Of Which Overdue', compute='_compute_x_customer_credit',
        currency_field='x_company_currency_id')
    x_customer_credit_open_count = fields.Integer(
        string='Open Credit Invoices', compute='_compute_x_customer_credit')

    @api.depends('x_credit_request_ids')
    def _compute_x_credit_request_count(self):
        for order in self:
            order.x_credit_request_count = len(order.x_credit_request_ids)

    @api.depends('partner_id', 'company_id')
    def _compute_x_customer_credit(self):
        Summary = self.env['customer.credit.summary'].sudo()
        for order in self:
            partner = order.partner_id.commercial_partner_id
            pos = Summary._position(partner, order.company_id) if partner \
                else Summary._empty_position()
            order.x_customer_credit_remaining = pos['remaining']
            order.x_customer_credit_overdue = pos['overdue']
            order.x_customer_credit_open_count = pos['open_invoice_count']

    @api.depends('payment_term_id')
    def _compute_x_sale_type(self):
        for order in self:
            order.x_sale_type = ('credit' if order.payment_term_id.x_is_credit
                                 else 'cash')

    def action_view_credit_requests(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'customer_credit_report.action_customer_credit_request')
        action['domain'] = [('sale_order_id', '=', self.id)]
        action['context'] = {'create': False}
        if len(self.x_credit_request_ids) == 1:
            action.update(view_mode='form',
                          views=[(False, 'form')],
                          res_id=self.x_credit_request_ids.id)
        return action

    def action_view_customer_credit(self):
        self.ensure_one()
        return self.partner_id.commercial_partner_id.action_view_credit_lines()

    def _create_credit_request(self):
        """Freeze the customer's credit position for this order and return
        the new Credit Sales Report (called when the salesperson sends the
        credit sale to the manager)."""
        Request = self.env['customer.credit.request'].sudo()
        requests = Request
        for order in self:
            # A resubmission replaces the previous pending report.
            order.x_credit_request_ids.sudo().filtered(
                lambda r: r.state == 'pending').write({'state': 'cancelled'})
            requests |= Request._create_for_order(order)
        return requests
