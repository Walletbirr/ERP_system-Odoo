from odoo import _, api, fields, models
from odoo.exceptions import UserError

CASH_KEYWORDS = ('immediate', 'cash')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_is_cash_sale = fields.Boolean(
        string='Cash Sale', compute='_compute_x_is_cash_sale',
        help='No payment term, or an "Immediate Payment" / "Cash" term, and '
             'not a credit term. Cash sales post one journal entry with the '
             'bank in place of the receivable.')

    @api.depends('payment_term_id', 'payment_term_id.name',
                 'x_is_credit_payment_term')
    def _compute_x_is_cash_sale(self):
        for order in self:
            term = order.payment_term_id
            name = (term.name or '').lower() if term else ''
            order.x_is_cash_sale = (
                not order.x_is_credit_payment_term
                and (not term or any(k in name for k in CASH_KEYWORDS)))

    @api.constrains('payment_term_id')
    def _check_payment_term_required(self):
        for order in self:
            if not order.payment_term_id:
                raise UserError(_(
                    "Payment Terms are required on a sales order: choose "
                    "Immediate Payment / Cash for a cash sale or a credit "
                    "term for a credit sale."))

    def action_confirm(self):
        # Quotations created before this rule may still have no term.
        for order in self:
            if not order.payment_term_id:
                raise UserError(_(
                    "%s has no Payment Terms. Set Immediate Payment / Cash "
                    "or a credit term before confirming.", order.name))
        return super().action_confirm()

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.x_is_cash_sale:
            vals.update(x_is_cash_sale=True, x_cash_order_id=self.id)
        return vals

    def _get_invoice_grouping_keys(self):
        # Every cash order gets its own invoice (its own bank rows).
        return super()._get_invoice_grouping_keys() + ['x_cash_order_id']

    def write(self, vals):
        before = {}
        if 'payment_term_id' in vals:
            before = {order.id: order.x_is_cash_sale for order in self}
        res = super().write(vals)
        for order in self:
            if order.id in before and before[order.id] != order.x_is_cash_sale:
                sudo = order.sudo()
                if (sudo.invoice_ids.filtered(lambda m: m.state != 'cancel')
                        or sudo.payment_proof_ids.filtered(
                            lambda p: p.state == 'approved')):
                    raise UserError(_(
                        "%s cannot change between cash and credit: its "
                        "payment has already been approved or invoiced.",
                        order.name))
        return res
