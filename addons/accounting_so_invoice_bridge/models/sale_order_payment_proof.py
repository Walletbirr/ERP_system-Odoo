import logging
from urllib.parse import quote

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

REVIEWER_GROUP = 'accounting_so_invoice_bridge.group_sale_invoice_creator'
REJECTED_SUMMARY = 'Payment proof rejected'
# To-Do for Accounting: a proof was submitted and waits for a decision.
REVIEW_PROOF_SUMMARY = 'Review payment proof'
# To-Do for Sales: Accounting approved, the invoice can now be created.
INVOICE_READY_SUMMARY = 'Payment approved: create the invoice'

# Only the Submit / Reopen / Approve / Reject buttons may change these.
PROTECTED_FIELDS = {
    'state', 'submitted_date', 'reviewed_by', 'reviewed_date',
    'reject_reason',
}
# The salesperson's content: frozen once submitted or approved.
CONTENT_FIELDS = {'proof_file', 'proof_filename', 'client_id_file',
                  'client_id_filename', 'notes'}


class SaleOrderPaymentProof(models.Model):
    _name = 'sale.order.payment.proof'
    _description = 'Sales Order Payment Proof'
    _order = 'uploaded_date desc, id desc'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    proof_file = fields.Binary(string='Proof File', attachment=True)
    proof_filename = fields.Char(string='Filename')
    client_id_file = fields.Binary(
        string='Client ID', attachment=True,
        help="Copy of the customer's ID document. Required together with "
             "the payment proof before the proof can be submitted.")
    client_id_filename = fields.Char(string='Client ID Filename')
    notes = fields.Text(
        string='Notes',
        help='Free text - any context the salesperson wants to add for '
             'Accounting (e.g. which bank/wallet the transfer came in on).',
    )
    state = fields.Selection(
        [('pending', 'Pending'),
         ('submitted', 'Awaiting Approval'),
         ('approved', 'Approved'),
         ('rejected', 'Rejected')],
        string='Status',
        default='pending',
        required=True,
        copy=False,
        help='Pending: the salesperson is still attaching the file. '
             'Awaiting Approval: submitted, Accounting must approve or '
             'reject it. Approved: Accounting accepted the payment. '
             'Rejected: sent back to the salesperson with a reason, who '
             'fixes the file and resubmits it.',
    )
    uploaded_by = fields.Many2one(
        'res.users', string='Uploaded By',
        default=lambda self: self.env.user, readonly=True)
    uploaded_date = fields.Datetime(
        string='Uploaded On', default=fields.Datetime.now, readonly=True)
    submitted_date = fields.Datetime(
        string='Submitted On', readonly=True, copy=False)
    reviewed_by = fields.Many2one(
        'res.users', string='Reviewed By', readonly=True, copy=False)
    reviewed_date = fields.Datetime(
        string='Reviewed On', readonly=True, copy=False)
    reject_reason = fields.Text(
        string='Rejection Reason', readonly=True, copy=False)
    client_id_link = fields.Html(
        string='Client ID',
        compute='_compute_download_link',
        sanitize=False,
        help='Server-built download link for the Client ID file.',
    )
    download_link = fields.Html(
        string='Payment Proof',
        compute='_compute_download_link',
        sanitize=False,
        help='Server-built filename + download link. A plain read-only '
             'Binary cell in a list view can be stuck showing only the '
             'file size, so this always resolves to a working link.',
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _is_reviewer(self, user=None):
        user = user or self.env.user
        return (user.has_group(REVIEWER_GROUP)
                or user.has_group('base.group_system'))

    def _check_reviewer(self):
        if not self._is_reviewer():
            raise AccessError(_(
                "Only Accounting can approve or reject a payment proof."))

    def _file_link(self, field_name, filename_field, default_name):
        self.ensure_one()
        if self[field_name] and isinstance(self.id, int):
            filename = self[filename_field] or default_name
            url = ('/web/content/sale.order.payment.proof/%s/%s'
                   '?download=true&filename=%s'
                   % (self.id, field_name, quote(filename)))
            return Markup(
                '<a href="%s" target="_blank" class="o_form_uri">'
                '<i class="fa fa-download me-1"/>%s</a>'
            ) % (url, escape(filename))
        return False

    @api.depends('proof_file', 'proof_filename',
                 'client_id_file', 'client_id_filename')
    def _compute_download_link(self):
        for proof in self:
            proof.download_link = proof._file_link(
                'proof_file', 'proof_filename', _('payment_proof'))
            proof.client_id_link = proof._file_link(
                'client_id_file', 'client_id_filename', _('client_id'))

    def _post_note(self, body):
        """Silent audit-trail note on the order and its draft invoices.
        Internal notes only: nobody is notified (Accounting is notified
        exactly once, when the invoice is created)."""
        for proof in self:
            order = proof.sale_order_id.sudo()
            order.message_post(body=body, subtype_xmlid='mail.mt_note')
            # message_post needs exactly one record: loop (there may be
            # no draft invoice yet, or several).
            for invoice in order.invoice_ids.filtered(
                    lambda m: m.state == 'draft'):
                invoice.message_post(body=body, subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------
    # Protection (server side - the view is only a convenience)
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            for vals in vals_list:
                for field_name in PROTECTED_FIELDS:
                    vals.pop(field_name, None)
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if PROTECTED_FIELDS & set(vals):
                raise UserError(_(
                    "The status of a payment proof can only be changed "
                    "with the Submit, Reopen, Approve and Reject buttons."))
            if CONTENT_FIELDS & set(vals) and any(
                    p.state in ('submitted', 'approved') for p in self):
                raise UserError(_(
                    "A submitted or approved payment proof cannot be "
                    "edited. Reopen it first (only possible before it is "
                    "approved)."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            if any(p.state in ('submitted', 'approved') for p in self):
                raise UserError(_(
                    "A submitted or approved payment proof cannot be "
                    "deleted."))
        return super().unlink()

    @api.constrains('sale_order_id')
    def _check_order_is_confirmed(self):
        for proof in self:
            if proof.sale_order_id.state != 'sale':
                raise UserError(_(
                    'A payment proof can only be added to a confirmed '
                    'Sales Order.'))

    # ------------------------------------------------------------------
    # Salesperson actions
    # ------------------------------------------------------------------
    def action_submit(self):
        """Pending -> Awaiting Approval, or Rejected -> resubmitted."""
        self.check_access('write')
        for proof in self:
            if proof.state not in ('pending', 'rejected'):
                raise UserError(_(
                    'Only a Pending or Rejected payment proof can be '
                    'submitted.'))
            if not proof.proof_file:
                raise UserError(_(
                    'Attach the payment proof file before submitting it '
                    'to Accounting.'))
            if not proof.client_id_file:
                raise UserError(_(
                    "Attach the client's ID as well before submitting the "
                    "payment proof to Accounting."))
        resubmitted = self.filtered(lambda p: p.state == 'rejected')
        self.sudo().write({
            'state': 'submitted',
            'submitted_date': fields.Datetime.now(),
            'reviewed_by': False,
            'reviewed_date': False,
            'reject_reason': False,
        })
        if resubmitted:
            resubmitted._close_rejected_activities()
            resubmitted._post_note(_(
                "%(user)s resubmitted a corrected payment proof.",
                user=self.env.user.name))
        else:
            self._post_note(_(
                "%(user)s submitted a payment proof for approval.",
                user=self.env.user.name))
        self._safe(self._notify_accounting_to_review)

    def action_reopen(self):
        """Self-service: pull a submitted (not yet approved) line back to
        fix a mistake."""
        self.check_access('write')
        for proof in self:
            if proof.state != 'submitted':
                raise UserError(_(
                    'Only a payment proof that is awaiting approval can be '
                    'reopened.'))
        self.sudo().write({'state': 'pending', 'submitted_date': False})
        self._safe(self._close_review_activities,
                   _("Withdrawn by the salesperson."))

    # ------------------------------------------------------------------
    # Accountant actions
    # ------------------------------------------------------------------
    def action_approve(self):
        self._check_reviewer()
        for proof in self:
            if proof.state != 'submitted':
                raise UserError(_(
                    'Only a payment proof that is awaiting approval can be '
                    'approved.'))
        self.sudo().write({
            'state': 'approved',
            'reviewed_by': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
            'reject_reason': False,
        })
        self._post_note(_(
            "%(user)s approved the payment proof.", user=self.env.user.name))
        self._safe(self._close_review_activities, _("Payment proof approved."))
        self._safe(self._notify_sales_approved)

    def action_open_reject_wizard(self):
        self._check_reviewer()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Payment Proof'),
            'res_model': 'sale.order.payment.proof.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_proof_ids': [(6, 0, self.ids)]},
        }

    def action_reject(self, reason):
        self._check_reviewer()
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_("Please give a reason for the rejection."))
        for proof in self:
            if proof.state != 'submitted':
                raise UserError(_(
                    'Only a payment proof that is awaiting approval can be '
                    'rejected.'))
        self.sudo().write({
            'state': 'rejected',
            'reviewed_by': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
            'reject_reason': reason,
        })
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for proof in self:
            order = proof.sale_order_id.sudo()
            assignee = (proof.uploaded_by if proof.uploaded_by.active else False) \
                or order.user_id
            if todo and assignee:
                order.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=assignee.id,
                    summary=REJECTED_SUMMARY,
                    note=_(
                        "%(user)s rejected the payment proof: %(reason)s. "
                        "Fix the file and submit it again.",
                        user=self.env.user.name, reason=reason),
                )
        self._post_note(_(
            "%(user)s rejected the payment proof: %(reason)s",
            user=self.env.user.name, reason=reason))
        self._safe(self._close_review_activities, _("Payment proof rejected."))

    def _close_rejected_activities(self):
        for order in self.sale_order_id.sudo():
            activities = order.activity_ids.filtered(
                lambda a: a.summary == REJECTED_SUMMARY)
            if activities:
                activities.action_feedback(
                    feedback=_("Corrected proof resubmitted."))

    # ------------------------------------------------------------------
    # Notifications (best effort: they must never break the workflow)
    # ------------------------------------------------------------------
    def _safe(self, method, *args):
        try:
            method(*args)
        except Exception:
            _logger.exception(
                "accounting_so_invoice_bridge: notification step %s failed "
                "- the workflow itself is unaffected.", method.__name__)

    @api.model
    def _get_reviewers(self):
        """Accountants (reviewer group); Settings Admins as a fallback."""
        Users = self.env['res.users'].sudo()
        group = self.env.ref(REVIEWER_GROUP, raise_if_not_found=False)
        users = Users.search([('groups_id', 'in', group.ids)]) if group else Users
        if not users:
            users = Users.search(
                [('groups_id', 'in', self.env.ref('base.group_system').ids)])
        return users

    def _toast(self, user, title, message):
        if 'bus.bus' in self.env:
            self.env['bus.bus'].sudo()._sendone(
                user.partner_id, 'simple_notification',
                {'type': 'info', 'title': title,
                 'message': message, 'sticky': False})

    def _notify_accounting_to_review(self):
        """Salesperson submitted (or resubmitted) a proof: one To-Do per
        accountant on the order, plus a live toast. Skipped if that
        accountant already has an open review To-Do on the order."""
        recipients = self._get_reviewers() - self.env.user
        if not recipients:
            return
        todo = self.env.ref('mail.mail_activity_data_todo',
                            raise_if_not_found=False)
        for order in self.sale_order_id.sudo():
            for user in recipients:
                open_todo = order.activity_ids.filtered(
                    lambda a: a.summary == REVIEW_PROOF_SUMMARY
                    and a.user_id == user)
                if todo and not open_todo:
                    order.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=user.id,
                        summary=REVIEW_PROOF_SUMMARY,
                        note=_("Open Payment Proofs, check the proof and the "
                               "client ID, then Approve or Reject."))
                self._toast(
                    user, _('Payment Proof to Review'),
                    _('%(order)s for %(customer)s is waiting for your '
                      'approval.', order=order.name,
                      customer=order.partner_id.display_name))

    def _close_review_activities(self, feedback):
        """Close Accounting's review To-Do once the order has no proof
        left awaiting a decision."""
        for order in self.sale_order_id.sudo():
            if order.payment_proof_ids.filtered(
                    lambda p: p.state == 'submitted'):
                continue
            acts = order.activity_ids.filtered(
                lambda a: a.summary == REVIEW_PROOF_SUMMARY)
            if acts:
                acts.action_feedback(feedback=feedback)

    def _notify_sales_approved(self):
        """All proofs of the order are Approved: tell the salesperson the
        invoice can now be created."""
        todo = self.env.ref('mail.mail_activity_data_todo',
                            raise_if_not_found=False)
        for order in self.sale_order_id.sudo():
            if (order.x_payment_proof_status != 'approved'
                    or order.invoice_status == 'invoiced'):
                continue
            users = (order.user_id | order.payment_proof_ids.uploaded_by)\
                .filtered('active')
            for user in users:
                open_todo = order.activity_ids.filtered(
                    lambda a: a.summary == INVOICE_READY_SUMMARY
                    and a.user_id == user)
                if todo and not open_todo:
                    order.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=user.id,
                        summary=INVOICE_READY_SUMMARY,
                        note=_("Accounting approved the payment proof. "
                               "Press Create Invoice."))
                self._toast(
                    user, _('Payment Proof Approved'),
                    _('%(order)s: approved by Accounting. You can create '
                      'the invoice now.', order=order.name))
