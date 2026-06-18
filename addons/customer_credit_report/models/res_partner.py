from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_total_sale_amount = fields.Monetary(
        string='Total Confirmed Sales',
        compute='_compute_x_total_sale_amount',
        currency_field='currency_id',
        help='Total amount of confirmed sale orders (Sales Orders, not '
             'quotations) for this customer.',
    )
    x_total_invoiced = fields.Monetary(
        string='Total Invoiced',
        compute='_compute_x_total_invoiced',
        currency_field='currency_id',
        help='Total amount invoiced to this customer (tax included), from '
             'all posted customer invoices and credit notes. Computed '
             'directly from invoices rather than the standard "Total '
             'Invoiced" field, which excludes tax and would not match '
             'sale order / payment amounts.',
    )
    x_credit_amount_paid = fields.Monetary(
        string='Amount Paid',
        compute='_compute_x_credit_amount_paid',
        currency_field='currency_id',
        help='Total invoiced amount (tax included) that has already been '
             'paid (Total Invoiced - Outstanding Credit).',
    )
    x_remaining_balance = fields.Monetary(
        string='Remaining Balance',
        compute='_compute_x_remaining_balance',
        currency_field='currency_id',
        help='Total amount the customer still owes overall: confirmed sale '
             'order amounts not yet invoiced, plus invoiced amounts not yet '
             'paid (Total Confirmed Sales - Amount Paid).',
    )

    @api.depends('sale_order_ids.amount_total', 'sale_order_ids.state')
    def _compute_x_total_sale_amount(self):
        for partner in self:
            orders = partner.sale_order_ids.filtered(
                lambda o: o.state == 'sale'
            )
            partner.x_total_sale_amount = sum(orders.mapped('amount_total'))

    @api.depends()
    def _compute_x_total_invoiced(self):
        AccountMove = self.env['account.move']
        for partner in self:
            invoices = AccountMove.search([
                ('partner_id', '=', partner.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
            ])
            total = 0.0
            for move in invoices:
                total += move.amount_total if move.move_type == 'out_invoice' \
                    else -move.amount_total
            partner.x_total_invoiced = total

    @api.depends('x_total_invoiced', 'credit')
    def _compute_x_credit_amount_paid(self):
        for partner in self:
            partner.x_credit_amount_paid = (
                partner.x_total_invoiced - partner.credit
            )

    @api.depends('x_total_sale_amount', 'x_credit_amount_paid')
    def _compute_x_remaining_balance(self):
        for partner in self:
            partner.x_remaining_balance = (
                partner.x_total_sale_amount - partner.x_credit_amount_paid
            )
