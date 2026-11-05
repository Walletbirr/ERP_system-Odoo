from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # --- Raw aggregates -----------------------------------------------
    deposit_total_paid = fields.Monetary(
        string='Total Paid (Inbound)',
        compute='_compute_deposit_amounts',
        store=True,
        currency_field='currency_id',
        help='Sum of all posted inbound customer payments received from this contact.',
    )
    deposit_total_invoiced = fields.Monetary(
        string='Total Invoiced',
        compute='_compute_deposit_amounts',
        store=True,
        currency_field='currency_id',
        help='Sum of all posted customer invoices for this contact.',
    )
    deposit_total_refunded = fields.Monetary(
        string='Total Refunded (Outbound)',
        compute='_compute_deposit_amounts',
        store=True,
        currency_field='currency_id',
        help='Sum of all posted outbound payments sent back to this customer '
             '(e.g. money returned from their deposit balance).',
    )
    deposit_balance = fields.Monetary(
        string='Deposit Balance',
        compute='_compute_deposit_amounts',
        store=True,
        currency_field='currency_id',
        help='Total Paid - Total Invoiced - Total Refunded. '
             'A positive value means the customer still has deposit credit with us.',
    )
    is_deposit_customer = fields.Boolean(
        string='Has Deposit Credit',
        compute='_compute_deposit_amounts',
        store=True,
        help='True when this customer has paid more than they have been invoiced for.',
    )
    deposit_last_transaction_date = fields.Datetime(
        string='Last Deposit Transaction',
        compute='_compute_deposit_amounts',
        store=True,
    )
    deposit_payment_count = fields.Integer(
        string='Deposit Payment Count',
        compute='_compute_deposit_amounts',
        store=True,
    )

    # --- Live relations used by the Customer Deposit Detail dashboard --
    deposit_invoice_ids = fields.One2many(
        'account.move', 'partner_id',
        string='Customer Invoices',
        domain=[('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted')],
    )
    deposit_payment_ids = fields.One2many(
        'account.payment', 'partner_id',
        string='Deposit Payments',
        domain=[('partner_type', '=', 'customer'), ('state', 'in', ('paid', 'in_process'))],
    )

    def _compute_deposit_amounts(self):
        Payment = self.env['account.payment'].sudo()
        Move = self.env['account.move'].sudo()
        for partner in self.sudo():
            if not partner.id:
                partner.deposit_total_paid = 0.0
                partner.deposit_total_invoiced = 0.0
                partner.deposit_total_refunded = 0.0
                partner.deposit_balance = 0.0
                partner.is_deposit_customer = False
                partner.deposit_last_transaction_date = False
                partner.deposit_payment_count = 0
                continue

            inbound_payments = Payment.search([
                ('partner_id', '=', partner.id),
                ('payment_type', '=', 'inbound'),
                ('partner_type', '=', 'customer'),
                ('state', 'in', ('paid', 'in_process')),
            ])
            outbound_payments = Payment.search([
                ('partner_id', '=', partner.id),
                ('payment_type', '=', 'outbound'),
                ('partner_type', '=', 'customer'),
                ('state', 'in', ('paid', 'in_process')),
            ])
            invoices = Move.search([
                ('partner_id', '=', partner.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
            ])

            total_paid = sum(inbound_payments.mapped('amount'))
            total_refunded = sum(outbound_payments.mapped('amount'))
            total_invoiced = sum(invoices.mapped('amount_total'))
            balance = total_paid - total_invoiced - total_refunded

            all_dates = inbound_payments.mapped('date') + outbound_payments.mapped('date')
            last_date = max(all_dates) if all_dates else False

            partner.deposit_total_paid = total_paid
            partner.deposit_total_invoiced = total_invoiced
            partner.deposit_total_refunded = total_refunded
            partner.deposit_balance = balance
            # small epsilon to avoid floating point noise flagging near-zero balances
            partner.is_deposit_customer = balance > 0.01
            partner.deposit_last_transaction_date = last_date
            partner.deposit_payment_count = len(inbound_payments) + len(outbound_payments)

    def action_recompute_deposit_balance(self):
        """Manual recompute button, and also callable from other models."""
        self._compute_deposit_amounts()
        return True

    def action_view_deposit_transactions(self):
        """Smart button action: open the payments (in & out) tied to this customer."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Deposit Transactions',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.id),
                ('partner_type', '=', 'customer'),
                ('state', 'in', ('paid', 'in_process')),
            ],
            'context': {'default_partner_id': self.id, 'default_partner_type': 'customer'},
        }

    @api.model
    def _cron_recompute_all_deposit_balances(self):
        """Nightly safety-net recompute for all customer contacts."""
        partners = self.search([('customer_rank', '>', 0)])
        partners._compute_deposit_amounts()
