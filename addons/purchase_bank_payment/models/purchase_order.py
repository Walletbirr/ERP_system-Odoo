from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    x_direct_pay = fields.Boolean(
        string="Pay Directly From Bank", default=True, copy=False,
        help="On: paid straight from the bank to GIT; vendor bills are "
             "hidden and blocked. Off: use Odoo's normal vendor bill, for a "
             "supplier who delivers on credit.")
    bank_payment_ids = fields.One2many(
        'purchase.bank.payment', 'purchase_id', string="Direct Payments")
    bank_paid_amount = fields.Monetary(
        string="Paid", currency_field='currency_id',
        compute='_compute_bank_payment', store=True)
    bank_remaining_amount = fields.Monetary(
        string="Remaining", currency_field='currency_id',
        compute='_compute_bank_payment', store=True)
    bank_payment_status = fields.Selection(
        [('not_paid', 'Not Paid'), ('partial', 'Partially Paid'),
         ('paid', 'Paid')],
        string="Payment Status", compute='_compute_bank_payment', store=True)
    bank_payment_count = fields.Integer(
        string="Payments", compute='_compute_bank_payment', store=True)
    bank_paid_percent = fields.Float(
        string="Paid %", compute='_compute_bank_payment', store=True)

    def _get_external_bank_payments(self):
        """Hook: (amount, count) paid by other sources (LC settlements),
        in the PO currency."""
        self.ensure_one()
        return 0.0, 0

    @api.depends('x_direct_pay', 'amount_total', 'currency_id',
                 'bank_payment_ids.state', 'bank_payment_ids.amount')
    def _compute_bank_payment(self):
        for po in self:
            local = po.bank_payment_ids.filtered(lambda p: p.state == 'posted')
            paid = sum(local.mapped('amount'))
            count = len(local)
            ext_amount, ext_count = po._get_external_bank_payments()
            paid += ext_amount
            count += ext_count
            total = po.amount_total
            cur = po.currency_id
            po.bank_paid_amount = paid
            po.bank_remaining_amount = max(total - paid, 0.0)
            po.bank_payment_count = count
            po.bank_paid_percent = min(paid / total * 100.0, 100.0) if total else 0.0
            if not cur or cur.is_zero(paid):
                po.bank_payment_status = 'not_paid'
            elif not total or cur.compare_amounts(paid, total) >= 0:
                po.bank_payment_status = 'paid'
            else:
                po.bank_payment_status = 'partial'

    def _bank_payments_action(self):
        """Default: this PO's direct payments. lc_management returns the LC
        settlements instead when the PO is paid through an LC."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Payments - %s", self.name),
            'res_model': 'purchase.bank.payment',
            'view_mode': 'list,form',
            'domain': [('purchase_id', '=', self.id)],
            'context': {'default_purchase_id': self.id},
        }

    def action_view_bank_payments(self):
        self.ensure_one()
        return self._bank_payments_action()

    def action_new_bank_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("New Payment"),
            'res_model': 'purchase.bank.payment',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_purchase_id': self.id,
                        'default_amount': self.bank_remaining_amount},
        }

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """Hide the bill buttons on direct-pay purchases, whatever their
        existing visibility rule is."""
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            for node in arch.xpath(
                    "//button[@name='action_create_invoice' "
                    "or @name='action_view_invoice' "
                    "or @name='action_register_payment']"):
                orig = node.get('invisible')
                node.set('invisible',
                         f"x_direct_pay or ({orig})" if orig else "x_direct_pay")
        return arch, view

    def action_create_invoice(self):
        if self.filtered('x_direct_pay'):
            raise UserError(_(
                "These purchases are paid directly from the bank, so no "
                "vendor bill is created. Use the Payments button, or untick "
                "'Pay Directly From Bank' for a credit supplier."))
        return super().action_create_invoice()
