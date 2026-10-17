import logging
from urllib.parse import quote

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import format_datetime, formatLang

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
    'reject_reason', 'payment_journal_id',
}
PREVIEW_IMAGE_EXT = ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg')
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
    payment_journal_id = fields.Many2one(
        'account.journal', string='Payment Journal', readonly=True,
        copy=False, domain="[('type', 'in', ('bank', 'cash'))]",
        help="Chosen by the accountant when approving: the journal the "
             "customer's payment went into. It comes preselected on the "
             "invoice's Pay dialog.")
    order_detail_html = fields.Html(
        string='Order Details', compute='_compute_order_detail_html',
        sanitize=False,
        help="Summary of the order behind this proof (customer, salesperson, "
             "branch, lines, totals). Sent to Accounting with the review "
             "request and shown on the proof so the accountant can decide "
             "without opening the order.")
    preview_links = fields.Html(
        string='Preview', compute='_compute_download_link', sanitize=False,
        help='Preview links for both files (used in the salesperson list).')
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

    def _file_url(self, field_name, filename, download):
        self.ensure_one()
        url = '/web/content/sale.order.payment.proof/%s/%s?filename=%s' % (
            self.id, field_name, quote(filename))
        if download:
            return url + '&download=true'
        # Inline URL (no download=true): the browser / our overlay shows
        # the file instead of saving it. The timestamp avoids a stale
        # cached copy after the file was replaced.
        stamp = int(self.write_date.timestamp()) if self.write_date else 0
        return '%s&ts=%s' % (url, stamp)

    def _preview_kind(self, filename):
        ext = (filename or '').rsplit('.', 1)[-1].lower() \
            if '.' in (filename or '') else ''
        if ext in PREVIEW_IMAGE_EXT:
            return 'image'
        if ext == 'pdf':
            return 'pdf'
        return False

    def _preview_anchor(self, field_name, filename_field, default_name,
                        label=None):
        """Eye icon that opens the file in the in-app viewer (or a new tab
        when JavaScript is not loaded). Empty if the file can not be
        shown inline (then only the download link exists)."""
        self.ensure_one()
        if not (self[field_name] and isinstance(self.id, int)):
            return Markup('')
        filename = self[filename_field] or default_name
        kind = self._preview_kind(filename)
        if not kind:
            return Markup('')
        return Markup(
            '<a href="%s" target="_blank" class="o_ab_preview me-2" '
            'data-ab-kind="%s" data-ab-title="%s" data-ab-download="%s" '
            'title="%s"><i class="fa fa-eye me-1"></i>%s</a>'
        ) % (self._file_url(field_name, filename, False), kind,
             filename, self._file_url(field_name, filename, True),
             _('Preview without downloading'),
             escape(label) if label else '')

    def _file_link(self, field_name, filename_field, default_name):
        self.ensure_one()
        if self[field_name] and isinstance(self.id, int):
            filename = self[filename_field] or default_name
            url = self._file_url(field_name, filename, True)
            return Markup(
                '%s<a href="%s" target="_blank" class="o_form_uri" '
                'title="%s"><i class="fa fa-download me-1"></i>%s</a>'
            ) % (self._preview_anchor(field_name, filename_field,
                                      default_name),
                 url, _('Download'), escape(filename))
        return False

    @api.depends('proof_file', 'proof_filename',
                 'client_id_file', 'client_id_filename')
    def _compute_download_link(self):
        for proof in self:
            proof.download_link = proof._file_link(
                'proof_file', 'proof_filename', _('payment_proof'))
            proof.client_id_link = proof._file_link(
                'client_id_file', 'client_id_filename', _('client_id'))
            parts = [
                proof._preview_anchor('proof_file', 'proof_filename',
                                      _('payment_proof'), _('Proof')),
                proof._preview_anchor('client_id_file', 'client_id_filename',
                                      _('client_id'), _('Client ID')),
            ]
            parts = [p for p in parts if p]
            proof.preview_links = Markup('').join(parts) if parts else False

    # ------------------------------------------------------------------
    # Order details (sent to Accounting with the review request)
    # ------------------------------------------------------------------
    @api.depends('sale_order_id')
    def _compute_order_detail_html(self):
        for proof in self:
            proof.order_detail_html = (
                proof._order_detail_html()
                if isinstance(proof.id, int) and proof.sale_order_id
                else False)

    def _order_detail_html(self):
        """Compact HTML summary of the order. Read with sudo: the
        accountant must see it even without Sales access."""
        self.ensure_one()
        order = self.sale_order_id.sudo()
        currency = order.currency_id

        def money(amount):
            return formatLang(self.env, amount, currency_obj=currency)

        th = 'border:1px solid #ccc;padding:3px 8px;background:#f2f2f2;'
        td = 'border:1px solid #ccc;padding:3px 8px;'
        facts = [
            (_('Order'), order.name),
            (_('Customer'), order.partner_id.display_name),
            (_('Salesperson'), order.user_id.name),
            (_('Order date'), format_datetime(self.env, order.date_order)
             if order.date_order else ''),
            (_('Branch'), order.x_sale_branch_id.display_name),
            (_('Deduction branch'), order.warehouse_id.display_name),
            (_('Payment terms'), order.payment_term_id.display_name),
            (_('Salesperson note'), self.notes),
        ]
        facts_html = Markup('').join(
            Markup('<tr><td style="%s;font-weight:bold">%s</td>'
                   '<td style="%s">%s</td></tr>') % (td, label, td, value)
            for label, value in facts if value)

        # "Selling Price" exists when custom_invoice_management_sale is there.
        line_model = self.env['sale.order.line']
        with_selling_price = 'cim_selling_price' in line_model._fields
        lines = order.order_line.filtered(
            lambda l: not l.display_type and l.product_id
            and not getattr(l, 'cim_hide_from_order_lines', False))
        head = [_('Product'), _('Qty'), _('Unit price'), _('Amount (incl. tax)')]
        if with_selling_price:
            head.append(_('Selling price'))
        head_html = Markup('').join(
            Markup('<th style="%s">%s</th>') % (th, h) for h in head)
        rows_html = Markup('')
        for line in lines:
            cells = [
                line.product_id.display_name,
                '%g %s' % (line.product_uom_qty, line.product_uom.name or ''),
                money(line.price_unit),
                money(line.price_total),
            ]
            if with_selling_price:
                cells.append(money(line['cim_selling_price']))
            rows_html += Markup('<tr>%s</tr>') % Markup('').join(
                Markup('<td style="%s">%s</td>') % (td, c) for c in cells)

        totals = [(_('Untaxed amount'), order.amount_untaxed),
                  (_('Taxes'), order.amount_tax),
                  (_('Total'), order.amount_total)]
        totals_html = Markup('').join(
            Markup('<tr><td style="%s;font-weight:bold">%s</td>'
                   '<td style="%s;text-align:right">%s</td></tr>')
            % (td, label, td, money(amount)) for label, amount in totals)

        return (
            Markup('<table style="border-collapse:collapse;margin-bottom:8px">'
                   '%s</table>') % facts_html
            + Markup('<table style="border-collapse:collapse;margin-bottom:8px">'
                     '<tr>%s</tr>%s</table>') % (head_html, rows_html)
            + Markup('<table style="border-collapse:collapse">%s</table>')
            % totals_html)

    def _proof_files_html(self):
        """Proof / Client ID links (eye = view without downloading)."""
        self.ensure_one()
        parts = []
        if self.download_link:
            parts.append(Markup('<b>%s</b> %s') % (
                _('Payment proof:'), Markup(self.download_link)))
        if self.client_id_link:
            parts.append(Markup('<b>%s</b> %s') % (
                _('Client ID:'), Markup(self.client_id_link)))
        return Markup('<br/>').join(parts)

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
    def action_open_approve_wizard(self):
        """Approve = pick the journal the payment arrived in first."""
        self._check_reviewer()
        for proof in self:
            if proof.state != 'submitted':
                raise UserError(_(
                    'Only a payment proof that is awaiting approval can be '
                    'approved.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approve Payment Proof'),
            'res_model': 'sale.order.payment.proof.approve.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_proof_ids': [(6, 0, self.ids)]},
        }

    def action_approve(self, journal=None):
        self._check_reviewer()
        if not journal:
            raise UserError(_(
                "Select the journal the payment was received in."))
        for proof in self:
            if proof.state != 'submitted':
                raise UserError(_(
                    'Only a payment proof that is awaiting approval can be '
                    'approved.'))
            if journal.type not in ('bank', 'cash') or (
                    journal.company_id != proof.sale_order_id.company_id):
                raise UserError(_(
                    "The journal must be a bank or cash journal of the "
                    "company of order %s.", proof.sale_order_id.name))
        self.sudo().write({
            'state': 'approved',
            'payment_journal_id': journal.id,
            'reviewed_by': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
            'reject_reason': False,
        })
        self._post_note(_(
            "%(user)s approved the payment proof (payment journal: "
            "%(journal)s).", user=self.env.user.name,
            journal=journal.display_name))
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
        """Salesperson submitted (or resubmitted) a proof: Accounting gets
        the ORDER DETAILS (a message on the order, so it reaches their
        inbox / email), one To-Do per accountant with the same details, and
        a live toast. A To-Do is skipped if that accountant already has an
        open review To-Do on the order; the message is sent every time, so
        a resubmission always arrives with the current order."""
        recipients = self._get_reviewers() - self.env.user
        if not recipients:
            return
        todo = self.env.ref('mail.mail_activity_data_todo',
                            raise_if_not_found=False)
        for order in self.sale_order_id.sudo():
            proofs = self.filtered(
                lambda p: p.sale_order_id.id == order.id).sudo()
            details = Markup('<p>%s</p>%s<p>%s</p>') % (
                _("%(user)s sent a payment proof for approval.",
                  user=self.env.user.name),
                Markup('<br/>').join(p._proof_files_html() for p in proofs),
                proofs[:1]._order_detail_html())
            order.message_post(
                subject=_("Payment proof to review: %s", order.name),
                body=details,
                partner_ids=recipients.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
                message_type='comment')
            for user in recipients:
                open_todo = order.activity_ids.filtered(
                    lambda a: a.summary == REVIEW_PROOF_SUMMARY
                    and a.user_id == user)
                if todo and not open_todo:
                    order.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=user.id,
                        summary=REVIEW_PROOF_SUMMARY,
                        note=Markup('<p>%s</p>%s') % (
                            _("Open Payment Proofs, check the proof and the "
                              "client ID, then Approve or Reject."),
                            proofs[:1]._order_detail_html()))
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
