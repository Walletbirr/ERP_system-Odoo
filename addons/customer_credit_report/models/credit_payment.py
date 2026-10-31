import logging

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

POST_SUMMARY = 'Post credit payment'
REJECTED_SUMMARY = 'Credit payment rejected'

# Accountants who post payments (accounting_so_invoice_bridge); without that
# module, the Accounting managers.
ACCOUNTANT_GROUPS = (
    'accounting_so_invoice_bridge.group_sale_invoice_creator',
    'account.group_account_manager',
)


class CustomerCreditPayment(models.Model):
    """A customer paid (part of) what they owe on credit.

    The salesperson records the amount and attaches the payment slip, then
    submits it. Accounting opens it, checks the slip and presses Post
    Payment, which opens Odoo's normal payment page for the customer's open
    credit invoices. The money always pays the OLDEST credit sale first,
    then the next one (see account_payment_register.py).
    """
    _name = 'customer.credit.payment'
    _description = 'Credit Payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', required=True, copy=False,
                       readonly=True, default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Waiting for Accounting'),
        ('posted', 'Posted'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, readonly=True, tracking=True,
        index=True, copy=False)
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, tracking=True,
        index=True, domain="[('is_company', '=', True)]")
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    user_id = fields.Many2one('res.users', string='Salesperson',
                              default=lambda self: self.env.user,
                              tracking=True)
    amount = fields.Monetary(string='Amount Paid', required=True,
                             tracking=True)
    payment_date = fields.Date(string='Paid On', required=True,
                               default=fields.Date.context_today,
                               tracking=True)
    journal_id = fields.Many2one(
        'account.journal', string='Paid Into (Bank)', tracking=True,
        domain="[('type', 'in', ('bank', 'cash')), "
               "('company_id', '=', company_id)]",
        help='Bank account / cash box the customer paid into, as on the '
             'slip. Accounting can still change it when posting.')
    reference = fields.Char(string='Slip / Transaction No.', tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'customer_credit_payment_attachment_rel',
        'payment_id', 'attachment_id', string='Payment Slip',
        help='Bank slip / transfer screenshot (PDF or image).')
    note = fields.Text()

    # Customer position, live (before posting) for the salesperson and
    # Accounting.
    owed = fields.Monetary(string='Customer Owes', compute='_compute_owed')
    allocation_html = fields.Html(string='Will Pay',
                                  compute='_compute_allocation',
                                  sanitize=False)

    # Accounting
    payment_id = fields.Many2one('account.payment', string='Payment',
                                 readonly=True, copy=False)
    posted_amount = fields.Monetary(related='payment_id.amount',
                                    string='Amount Posted')
    reviewed_by_id = fields.Many2one('res.users', string='Reviewed By',
                                     readonly=True, copy=False)
    reviewed_date = fields.Datetime(readonly=True, copy=False)
    reject_reason = fields.Text(readonly=True, copy=False)
    settlement_ids = fields.Many2many(
        'customer.credit.settlement', compute='_compute_settlement_ids',
        string='Applied To')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'customer.credit.payment') or _('New')
        records = super().create(vals_list)
        records._attach_files()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'attachment_ids' in vals:
            self._attach_files()
        return res

    def _attach_files(self):
        for rec in self:
            rec.attachment_ids.filtered(lambda a: not a.res_id).sudo().write(
                {'res_model': self._name, 'res_id': rec.id})

    def unlink(self):
        if any(rec.state not in ('draft', 'cancelled') for rec in self):
            raise UserError(_("Only draft or cancelled credit payments can "
                              "be deleted."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    def _open_credit_lines(self):
        """The customer's open credit invoices, oldest credit sale first
        (the order the money pays them)."""
        self.ensure_one()
        if not self.partner_id:
            return self.env['customer.credit.line']
        self.env.flush_all()
        Line = self.env['customer.credit.line'].sudo()
        Line.invalidate_model()
        return Line.search([
            ('partner_id', '=', self.partner_id.commercial_partner_id.id),
            ('company_id', '=', self.company_id.id),
            ('move_type', '=', 'out_invoice'),
            ('amount_residual', '>', 0),
        ], order='invoice_date asc, id asc')

    @api.depends('partner_id', 'company_id', 'state')
    def _compute_owed(self):
        Summary = self.env['customer.credit.summary'].sudo()
        for rec in self:
            rec.owed = Summary._position(
                rec.partner_id, rec.company_id)['remaining'] \
                if rec.partner_id else 0.0

    @api.depends('partner_id', 'company_id', 'amount', 'state')
    def _compute_allocation(self):
        for rec in self:
            if rec.state == 'posted' or not rec.partner_id:
                rec.allocation_html = False
                continue
            left = rec.amount or 0.0
            cur = rec.currency_id
            rows = []
            for line in rec._open_credit_lines():
                pay = min(left, line.amount_residual) if left > 0 else 0.0
                left -= pay
                rows.append(
                    '<tr><td>%s</td><td>%s</td><td>%s</td>'
                    '<td class="text-end">%s</td>'
                    '<td class="text-end fw-bold">%s</td>'
                    '<td class="text-end">%s</td></tr>' % (
                        escape(line.move_id.name), escape(line.origin or ''),
                        line.invoice_date.strftime('%d/%m/%Y')
                        if line.invoice_date else '',
                        escape(cur.format(line.amount_residual)),
                        escape(cur.format(pay)) if pay else '-',
                        escape(cur.format(line.amount_residual - pay))))
            if not rows:
                rec.allocation_html = Markup(
                    '<p class="text-muted">%s</p>') % _(
                    "This customer has no open credit invoice.")
                continue
            extra = ''
            if left > 0.005:
                extra = '<p class="text-warning mt-2">%s</p>' % escape(_(
                    "%s more than the customer owes: it stays on the "
                    "customer's account as an unmatched payment.",
                    cur.format(left)))
            rec.allocation_html = Markup(
                '<table class="table table-sm o_credit_allocation">'
                '<thead><tr><th>%s</th><th>%s</th><th>%s</th>'
                '<th class="text-end">%s</th><th class="text-end">%s</th>'
                '<th class="text-end">%s</th></tr></thead><tbody>%s'
                '</tbody></table>%s' % (
                    escape(_('Invoice')), escape(_('Sales Order')),
                    escape(_('Invoice Date')), escape(_('Unpaid')),
                    escape(_('This Payment')), escape(_('Left After')),
                    ''.join(rows), extra))

    def _compute_settlement_ids(self):
        Settlement = self.env['customer.credit.settlement']
        for rec in self:
            rec.settlement_ids = Settlement.search(
                [('payment_move_id', '=', rec.payment_id.move_id.id)]) \
                if rec.payment_id else Settlement

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _accountant_users(self):
        for xmlid in ACCOUNTANT_GROUPS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            users = group.sudo().users.filtered('active') if group else False
            if users:
                return users.filtered(lambda u: not u.share)
        return self.env['res.users']

    def action_submit(self):
        for rec in self:
            if rec.state not in ('draft', 'rejected'):
                raise UserError(_("%s was already sent to Accounting.",
                                  rec.name))
            if rec.currency_id.compare_amounts(rec.amount, 0) <= 0:
                raise UserError(_("Enter the amount the customer paid."))
            if not rec.attachment_ids:
                raise UserError(_(
                    "Attach the payment slip (PDF or image) before sending "
                    "it to Accounting."))
            if not rec._open_credit_lines():
                raise UserError(_(
                    "%s has no open credit invoice to pay.",
                    rec.partner_id.display_name))
            rec.write({'state': 'submitted', 'reject_reason': False})
            rec.activity_ids.filtered(
                lambda a: a.summary == REJECTED_SUMMARY).action_feedback(
                feedback=_("Sent to Accounting again."))
            note = _(
                "%(customer)s paid %(amount)s on %(date)s. Check the slip, "
                "then press Post Payment.",
                customer=rec.partner_id.display_name,
                amount=rec.currency_id.format(rec.amount),
                date=rec.payment_date.strftime('%d/%m/%Y'))
            for user in rec._accountant_users():
                rec.activity_schedule('mail.mail_activity_data_todo',
                                      user_id=user.id, summary=POST_SUMMARY,
                                      note=note)
            rec.message_post(body=_("Sent to Accounting."),
                             subtype_xmlid='mail.mt_note')
        return True

    def action_post_payment(self):
        """Odoo's payment page for the customer's open credit invoices,
        filled in from this request. The payment pays the oldest credit
        sale first."""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_("Only payments waiting for Accounting can be "
                              "posted."))
        lines = self._open_credit_lines()
        if not lines:
            raise UserError(_(
                "%s has no open credit invoice anymore.",
                self.partner_id.display_name))
        receivable = lines.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and not l.reconciled)
        ctx = {
            'credit_payment_request_id': self.id,
            'default_amount': self.amount,
            'default_custom_user_amount': self.amount,
            'default_payment_date': self.payment_date,
            'default_group_payment': True,
            'default_communication': ' - '.join(
                p for p in (self.reference, self.name) if p),
        }
        if self.journal_id:
            ctx['default_journal_id'] = self.journal_id.id
        action = receivable.action_register_payment(ctx=ctx)
        action['name'] = _('Post Credit Payment %s', self.name)
        return action

    def _on_payment_created(self, payments):
        """Called by the payment page once Accounting created the
        payment."""
        self.ensure_one()
        payment = payments[:1]
        self.write({
            'state': 'posted',
            'payment_id': payment.id,
            'reviewed_by_id': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
        })
        self.activity_ids.filtered(
            lambda a: a.summary == POST_SUMMARY).action_feedback(
            feedback=_("Payment %s posted.", payment.name))
        self._notify_salesperson(
            _("Payment posted: %(amount)s from %(customer)s (%(payment)s).",
              amount=self.currency_id.format(payment.amount),
              customer=self.partner_id.display_name, payment=payment.name))

    def action_reject(self, reason):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Only payments waiting for Accounting can "
                                  "be rejected."))
            rec.write({
                'state': 'rejected',
                'reject_reason': reason,
                'reviewed_by_id': self.env.user.id,
                'reviewed_date': fields.Datetime.now(),
            })
            rec.activity_ids.filtered(
                lambda a: a.summary == POST_SUMMARY).action_feedback(
                feedback=_("Rejected: %s", reason))
            if rec.user_id.active:
                rec.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=rec.user_id.id,
                    summary=REJECTED_SUMMARY,
                    note=_("Accounting rejected %(name)s: %(reason)s. Fix it "
                           "and send it again.", name=rec.name,
                           reason=reason))
            rec._notify_salesperson(_("Rejected by Accounting: %s", reason))
        return True

    def action_open_reject(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Credit Payment'),
            'res_model': 'customer.credit.payment.reject',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_payment_request_id': self.id},
        }

    def action_cancel(self):
        for rec in self:
            if rec.state == 'posted':
                raise UserError(_("A posted payment cannot be cancelled "
                                  "here; Accounting reverses the payment."))
            rec.state = 'cancelled'
            rec.activity_ids.unlink()
        return True

    def action_reset_draft(self):
        self.filtered(lambda r: r.state in ('rejected', 'cancelled')).write(
            {'state': 'draft'})
        return True

    def _notify_salesperson(self, body):
        self.ensure_one()
        try:
            partners = self.user_id.partner_id
            self.message_post(body=body, partner_ids=partners.ids,
                              subtype_xmlid='mail.mt_comment')
        except Exception:
            _logger.exception("customer_credit_report: could not notify the "
                              "salesperson about %s", self.name)

    def action_open_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': self.payment_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }


class CustomerCreditPaymentReject(models.TransientModel):
    _name = 'customer.credit.payment.reject'
    _description = 'Reject Credit Payment'

    payment_request_id = fields.Many2one('customer.credit.payment',
                                         required=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.payment_request_id.action_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
