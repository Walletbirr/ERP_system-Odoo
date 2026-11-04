import logging

from markupsafe import Markup, escape

from odoo import Command, _, api, fields, models
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

    The salesperson records the amount, attaches the payment slip and
    chooses what the money pays (previous balance and/or credit sales,
    pre-filled oldest first; a note is required when a newer item is paid
    before an older one), then submits it. Accounting checks the slip and
    presses Post Payment, which posts it exactly as split.
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
    previous_balance = fields.Monetary(string='Previous Balance',
                                       compute='_compute_owed')

    # What the money pays: chosen by the salesperson (pre-filled oldest
    # first). Paying a newer item while an older one stays unpaid needs a
    # note.
    allocation_ids = fields.One2many(
        'customer.credit.payment.allocation', 'payment_request_id',
        string='Pays', copy=False)
    allocated_total = fields.Monetary(compute='_compute_allocated_total',
                                      string='Allocated')
    not_oldest_first = fields.Boolean(
        compute='_compute_allocated_total',
        help='Money goes to a newer item while an older one stays unpaid.')
    order_note = fields.Text(
        string='Why Not Oldest First', tracking=True,
        help='Required when the payment pays a newer credit sale while an '
             'older one (or the previous balance) stays unpaid.')

    # Accounting
    payment_id = fields.Many2one('account.payment', string='Payment',
                                 readonly=True, copy=False)
    payment_ids = fields.Many2many(
        'account.payment', 'customer_credit_payment_account_payment_rel',
        'request_id', 'payment_id', string='Payments', readonly=True,
        copy=False)
    posted_amount = fields.Monetary(compute='_compute_posted_amount',
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
    def _open_items(self):
        """What the customer can pay, oldest first: the previous balance
        (customers with their own Credit Account) then the open credit
        invoices by invoice date. customer.credit.line records."""
        self.ensure_one()
        if not self.partner_id:
            return self.env['customer.credit.line']
        self.env.flush_all()
        Line = self.env['customer.credit.line'].sudo()
        Line.invalidate_model()
        items = Line.search([
            ('partner_id', '=', self.partner_id.commercial_partner_id.id),
            ('company_id', '=', self.company_id.id),
            ('move_type', 'in', ('out_invoice', 'previous')),
            ('amount_residual', '>', 0),
        ])
        return items.sorted(lambda l: (
            0 if l.move_type == 'previous' else 1,
            l.invoice_date or fields.Date.today(), l.id))

    def _open_credit_lines(self):
        """Open credit invoices only (kept for other modules)."""
        return self._open_items().filtered(
            lambda l: l.move_type == 'out_invoice')

    @api.depends('partner_id', 'company_id', 'state')
    def _compute_owed(self):
        Summary = self.env['customer.credit.summary'].sudo()
        for rec in self:
            pos = Summary._position(rec.partner_id, rec.company_id) \
                if rec.partner_id else Summary._empty_position()
            rec.owed = pos['remaining']
            rec.previous_balance = pos['previous']

    @api.depends('allocation_ids.amount', 'allocation_ids.unpaid')
    def _compute_allocated_total(self):
        for rec in self:
            rec.allocated_total = sum(rec.allocation_ids.mapped('amount'))
            rec.not_oldest_first = rec._skips_older()

    def _skips_older(self):
        """True when a newer item gets money while an older one is left
        (partly) unpaid."""
        self.ensure_one()
        cur = self.currency_id
        left_unpaid = False
        for alloc in self.allocation_ids.sorted(
                lambda a: (a.sequence, a.id or 0)):
            paid = cur.compare_amounts(alloc.amount, 0) > 0
            if paid and left_unpaid:
                return True
            if cur.compare_amounts(alloc.amount, alloc.unpaid) < 0:
                left_unpaid = True
        return False

    def _compute_posted_amount(self):
        for rec in self:
            rec.posted_amount = sum(rec.payment_ids.mapped('amount')) \
                or rec.payment_id.amount

    def _allocation_commands(self):
        """Fresh allocation lines: every open item, the amount spread
        oldest first."""
        self.ensure_one()
        left = self.amount or 0.0
        commands = [Command.clear()]
        for seq, item in enumerate(self._open_items(), start=1):
            pay = min(left, item.amount_residual) if left > 0 else 0.0
            left -= pay
            commands.append(Command.create({
                'sequence': seq,
                'kind': 'previous' if item.move_type == 'previous'
                else 'invoice',
                'move_id': item.move_id.id,
                'item_date': item.invoice_date,
                'unpaid': item.amount_residual,
                'amount': self.currency_id.round(pay),
            }))
        return commands

    @api.onchange('partner_id', 'company_id', 'amount')
    def _onchange_fill_allocation(self):
        if self.state in ('draft', 'rejected'):
            self.allocation_ids = self._allocation_commands()

    def action_fill_oldest_first(self):
        for rec in self:
            if rec.state not in ('draft', 'rejected'):
                continue
            rec.allocation_ids = rec._allocation_commands()
        return True

    def _refresh_unpaid(self):
        """Bring each line's Unpaid up to date (things may have been paid
        since). Raise if an item is no longer open."""
        self.ensure_one()
        items = self._open_items()
        previous = items.filtered(lambda l: l.move_type == 'previous')
        by_move = {l.move_id.id: l for l in items if l.move_id}
        for alloc in self.allocation_ids:
            item = previous[:1] if alloc.kind == 'previous' \
                else by_move.get(alloc.move_id.id)
            unpaid = item.amount_residual if item else 0.0
            if alloc.unpaid != unpaid:
                alloc.unpaid = unpaid

    def _check_allocation(self):
        self.ensure_one()
        cur = self.currency_id
        self._refresh_unpaid()
        allocs = self.allocation_ids.filtered(
            lambda a: cur.compare_amounts(a.amount, 0) != 0)
        if not allocs:
            raise UserError(_(
                "Choose what this payment pays (previous balance and/or "
                "credit sales)."))
        for alloc in allocs:
            if cur.compare_amounts(alloc.amount, 0) < 0:
                raise UserError(_("Amounts cannot be negative."))
            if cur.compare_amounts(alloc.amount, alloc.unpaid) > 0:
                raise UserError(_(
                    "%(item)s: %(amount)s is more than what is unpaid "
                    "(%(unpaid)s).", item=alloc.label,
                    amount=cur.format(alloc.amount),
                    unpaid=cur.format(alloc.unpaid)))
        if cur.compare_amounts(sum(allocs.mapped('amount')),
                               self.amount) != 0:
            raise UserError(_(
                "The amounts chosen (%(chosen)s) must add up to the amount "
                "paid (%(paid)s).",
                chosen=cur.format(sum(allocs.mapped('amount'))),
                paid=cur.format(self.amount)))
        if self._skips_older() and not (self.order_note or '').strip():
            raise UserError(_(
                "This payment pays a newer item while an older one stays "
                "unpaid. Write why in \"Why Not Oldest First\" (for "
                "example: the customer asked to pay the October sale "
                "first)."))

    def _compute_settlement_ids(self):
        Settlement = self.env['customer.credit.settlement']
        for rec in self:
            moves = (rec.payment_ids | rec.payment_id).move_id
            rec.settlement_ids = Settlement.search(
                [('payment_move_id', 'in', moves.ids)]) \
                if moves else Settlement

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
            if not rec._open_items():
                raise UserError(_(
                    "%s owes nothing on credit.",
                    rec.partner_id.display_name))
            if not rec.allocation_ids:
                rec.allocation_ids = rec._allocation_commands()
            rec._check_allocation()
            rec.write({'state': 'submitted', 'reject_reason': False})
            rec.activity_ids.filtered(
                lambda a: a.summary == REJECTED_SUMMARY).action_feedback(
                feedback=_("Sent to Accounting again."))
            note = _(
                "%(customer)s paid %(amount)s on %(date)s for: %(what)s. "
                "Check the slip, then press Post Payment.",
                customer=rec.partner_id.display_name,
                amount=rec.currency_id.format(rec.amount),
                date=rec.payment_date.strftime('%d/%m/%Y'),
                what=rec._allocation_text())
            for user in rec._accountant_users():
                rec.activity_schedule('mail.mail_activity_data_todo',
                                      user_id=user.id, summary=POST_SUMMARY,
                                      note=note)
            rec.message_post(body=_("Sent to Accounting."),
                             subtype_xmlid='mail.mt_note')
        return True

    def _allocation_text(self):
        self.ensure_one()
        cur = self.currency_id
        return ', '.join(
            '%s %s' % (a.label, cur.format(a.amount))
            for a in self.allocation_ids.sorted('sequence')
            if cur.compare_amounts(a.amount, 0) > 0)

    def action_post_payment(self):
        """Post the payment as the salesperson split it: one payment per
        line. Money for a credit sale is matched to that invoice; money for
        the previous balance stays on the customer's Credit Account
        (matched to its old open amounts when there are any)."""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_("Only payments waiting for Accounting can be "
                              "posted."))
        if not self.journal_id:
            raise UserError(_(
                "Choose the bank / cash journal the money was paid into "
                "(Paid Into) before posting."))
        if not self.allocation_ids:
            # Sent before this version: split it oldest first.
            self.allocation_ids = self._allocation_commands()
        self._check_allocation()
        memo = ' - '.join(p for p in (self.reference, self.name) if p)
        payments = self.env['account.payment']
        cur = self.currency_id
        for alloc in self.allocation_ids.sorted('sequence'):
            if cur.compare_amounts(alloc.amount, 0) <= 0:
                continue
            if alloc.kind == 'previous':
                payments |= self._post_previous_payment(alloc, memo)
            else:
                payments |= self._post_invoice_payment(alloc, memo)
        self._on_payment_created(payments)
        return True

    def _post_invoice_payment(self, alloc, memo):
        lines = alloc.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and not l.reconciled)
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move.line', active_ids=lines.ids,
        ).create({
            'amount': alloc.amount,
            'payment_date': self.payment_date,
            'journal_id': self.journal_id.id,
            'communication': memo,
            'group_payment': True,
            'payment_difference_handling': 'open',
        })
        return wizard._create_payments()

    def _post_previous_payment(self, alloc, memo):
        partner = self.partner_id.commercial_partner_id.with_company(
            self.company_id)
        account = partner.x_credit_account_id
        if not account:
            raise UserError(_("%s has no Credit Account.",
                              partner.display_name))
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': alloc.amount,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'memo': memo,
            'destination_account_id': account.id,
            'company_id': self.company_id.id,
        })
        payment.action_post()
        # Match it with the old open amounts on the account, oldest first,
        # so it is not left as an "outstanding credit" someone could apply
        # to a new invoice by mistake.
        pay_line = payment.move_id.line_ids.filtered(
            lambda l: l.account_id == account)
        old = self.env['account.move.line'].search([
            ('account_id', '=', account.id),
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '>', 0),
            '|', ('move_id.move_type', 'not in',
                  ('out_invoice', 'out_refund')),
            ('move_id.x_sale_type', '!=', 'credit'),
        ], order='date asc, id asc')
        if old and pay_line:
            (pay_line + old).reconcile()
        return payment

    def _on_payment_created(self, payments):
        """Called once Accounting posted the payment(s)."""
        self.ensure_one()
        self.write({
            'state': 'posted',
            'payment_id': payments[:1].id,
            'payment_ids': [Command.set(payments.ids)],
            'reviewed_by_id': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
        })
        names = ', '.join(payments.mapped('name'))
        self.activity_ids.filtered(
            lambda a: a.summary == POST_SUMMARY).action_feedback(
            feedback=_("Payment %s posted.", names))
        self._notify_salesperson(
            _("Payment posted: %(amount)s from %(customer)s for %(what)s.",
              amount=self.currency_id.format(sum(payments.mapped('amount'))),
              customer=self.partner_id.display_name,
              what=self._allocation_text()))

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
        payments = self.payment_ids or self.payment_id
        if len(payments) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'res_id': payments.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payments'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', payments.ids)],
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


class CustomerCreditPaymentAllocation(models.Model):
    """One item a credit payment pays: the previous balance or a credit
    sale (invoice)."""
    _name = 'customer.credit.payment.allocation'
    _description = 'Credit Payment - What It Pays'
    _order = 'sequence, id'

    payment_request_id = fields.Many2one(
        'customer.credit.payment', required=True, ondelete='cascade',
        index=True)
    sequence = fields.Integer(default=10)
    currency_id = fields.Many2one(related='payment_request_id.currency_id')
    kind = fields.Selection([('previous', 'Previous Balance'),
                             ('invoice', 'Credit Sale')],
                            required=True, default='invoice')
    move_id = fields.Many2one('account.move', string='Invoice',
                              readonly=True)
    item_date = fields.Date(string='Date', readonly=True)
    label = fields.Char(string='Pays', compute='_compute_label')
    unpaid = fields.Monetary(string='Unpaid', readonly=True)
    amount = fields.Monetary(string='This Payment')

    @api.depends('kind', 'item_date', 'move_id')
    def _compute_label(self):
        for rec in self:
            if rec.kind == 'previous':
                rec.label = _('Previous balance')
            else:
                rec.label = _('Sale of %s', rec.item_date.strftime(
                    '%d/%m/%Y')) if rec.item_date else rec.move_id.name
