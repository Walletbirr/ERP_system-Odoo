from odoo import Command, _, api, models
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    """Credit invoices are paid oldest credit sale first.

    However the payment is registered (a Credit Payment from Sales, or the
    Pay button on invoices), money received from a customer on credit pays
    their first credit sale, then the next one.
    """
    _inherit = 'account.payment.register'

    def _credit_moves(self):
        return self.line_ids.move_id.filtered(
            lambda m: m.move_type == 'out_invoice'
            and m.x_sale_type == 'credit')

    def _check_credit_oldest_first(self):
        for wizard in self:
            moves = wizard._credit_moves()
            if not moves:
                continue
            Move = self.env['account.move'].sudo()
            for partner in moves.commercial_partner_id:
                mine = moves.filtered(
                    lambda m: m.commercial_partner_id == partner)
                newest = max(mine, key=lambda m: (m.invoice_date, m.id))
                older = Move.search([
                    ('commercial_partner_id', '=', partner.id),
                    ('company_id', '=', newest.company_id.id),
                    ('move_type', '=', 'out_invoice'),
                    ('x_sale_type', '=', 'credit'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ('not_paid', 'partial')),
                    ('id', 'not in', mine.ids),
                    '|', ('invoice_date', '<', newest.invoice_date),
                    '&', ('invoice_date', '=', newest.invoice_date),
                    ('id', '<', newest.id),
                ], order='invoice_date asc, id asc')
                if older:
                    raise UserError(_(
                        "%(customer)s still owes on older credit sales: "
                        "%(older)s.\nPayments pay the oldest credit sale "
                        "first. Select those invoices too (or use a Credit "
                        "Payment from Sales).",
                        customer=partner.display_name,
                        older=', '.join(older.mapped('name'))))

    @api.depends('can_edit_wizard', 'amount')
    def _compute_communication(self):
        super()._compute_communication()
        memo = self.env.context.get('credit_payment_request_id') \
            and self.env.context.get('default_communication')
        if memo:
            # Credit Payment from Sales: keep its slip number / reference.
            for wizard in self:
                wizard.communication = memo

    def action_create_payments(self):
        self._check_credit_oldest_first()
        return super().action_create_payments()

    def _create_payments(self):
        payments = super()._create_payments()
        request_id = self.env.context.get('credit_payment_request_id')
        if request_id and payments:
            request = self.env['customer.credit.payment'].browse(request_id)
            if request.exists() and request.state == 'submitted':
                request._on_payment_created(payments)
        return payments

    def _reconcile_payments(self, to_process, edit_mode=False):
        """Several credit invoices in one payment: match them one by one,
        oldest credit sale first (Odoo would go by due date)."""
        credit, others = [], []
        for vals in to_process:
            moves = vals['to_reconcile'].move_id
            if len(moves) > 1 and all(
                    m.move_type == 'out_invoice' and m.x_sale_type == 'credit'
                    for m in moves):
                credit.append(vals)
            else:
                others.append(vals)
        if others:
            super()._reconcile_payments(others, edit_mode=edit_mode)
        domain = [
            ('parent_state', '=', 'posted'),
            ('account_type', 'in',
             self.env['account.payment']._get_valid_payment_account_types()),
            ('reconciled', '=', False),
        ]
        for vals in credit:
            payment = vals['payment']
            extra = ({'forced_rate_from_register_payment': vals['rate']}
                     if 'rate' in vals else {})
            lines = vals['to_reconcile'].sorted(lambda l: (
                l.move_id.invoice_date, l.move_id.id,
                l.date_maturity or l.date, l.id))
            paid = self.env['account.move']
            for line in lines:
                if line.reconciled:
                    continue
                pay_lines = payment.move_id.line_ids.filtered_domain(
                    domain + [('account_id', '=', line.account_id.id)])
                if not pay_lines:
                    break
                (pay_lines + line).with_context(**extra).reconcile()
                paid |= line.move_id
            paid.matched_payment_ids = [Command.link(payment.id)]
