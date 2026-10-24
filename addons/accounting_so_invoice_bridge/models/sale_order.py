import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .sale_order_payment_proof import INVOICE_READY_SUMMARY

_logger = logging.getLogger(__name__)

REVIEWER_GROUP = 'accounting_so_invoice_bridge.group_sale_invoice_creator'
# To-Do for Sales: the High-Level Manager rejected the order.
MANAGER_REJECTED_SUMMARY = 'Manager rejected the order'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Orders still confirm directly (no manager approval at confirmation:
    # requires_credit_approval stays False). The High-Level Manager
    # (sale_credit_approval) now decides AFTER Accounting approved the
    # payment proof and BEFORE the salesperson may create the invoice, see
    # _request_manager_after_payment() and x_invoice_unlocked.
    requires_credit_approval = fields.Boolean(default=False)

    can_create_invoice = fields.Boolean(
        compute='_compute_can_create_invoice',
        string='Can Create Invoice (internal)',
        help='True for Salespeople (they create the draft invoice that '
             'Accounting then reviews), for Accounting users holding the '
             'dedicated accountant group, and for Settings Administrators. '
             'Deliberately ignores Odoo\'s native Invoicing field. The '
             'native "Create Invoice" buttons are shown only when this is '
             'true.',
    )

    payment_proof_ids = fields.One2many(
        'sale.order.payment.proof', 'sale_order_id', string='Payment Proofs',
        help='Payment-proof files the salesperson attaches once the '
             'customer has paid. Each one goes Pending -> Awaiting '
             'Approval -> Approved (or Rejected, with a reason, and back).',
    )
    x_has_payment_proof = fields.Boolean(
        compute='_compute_x_payment_proof', store=True,
        string='Payment Proof Attached',
        help='At least one payment proof line exists, in any status.',
    )
    x_has_submitted_payment_proof = fields.Boolean(
        compute='_compute_x_payment_proof', store=True,
        string='Payment Proof Submitted',
        help='At least one payment proof has been submitted to '
             'Accounting (awaiting approval or already approved).',
    )
    x_payment_proof_status = fields.Selection(
        [('none', 'Not Uploaded'),
         ('pending', 'Pending'),
         ('rejected', 'Rejected'),
         ('submitted', 'Awaiting Approval'),
         ('approved', 'Approved')],
        compute='_compute_x_payment_proof', store=True,
        string='Payment Proof Status', default='none',
        help='Overall status of the order\'s payment proofs, worst first: '
             'any Rejected, else any Pending, else any Awaiting Approval, '
             'else Approved (all of them). Not Uploaded when there are '
             'none.',
    )

    x_invoice_unlocked = fields.Boolean(
        compute='_compute_x_invoice_unlocked',
        string='Invoice Unlocked (internal)',
        help='True once Accounting approved every payment proof of the '
             'order AND the High-Level Manager approved the order (Credit '
             'orders need neither: always unlocked). The Create Invoice '
             'buttons and the server-side check use it.',
    )

    payment_proof_editable = fields.Boolean(
        compute='_compute_payment_proof_editable',
        string='Payment Proof Editable (internal)',
        help='Drives the single payment_proof_ids list in the view. '
             'Settings Administrators: editable. Anyone in the accountant '
             'group: read-only (Approve / Reject only), even if they also '
             'hold a Sales group. Otherwise editable only for '
             'Salespeople.',
    )

    x_is_credit_payment_term = fields.Boolean(
        compute='_compute_x_is_credit_payment_term',
        string='Credit Payment Term (internal)',
        help='True only when the Payment Terms name contains the word '
             '"credit" (case-insensitive), e.g. "Credit 30 Days". Credit '
             'orders skip the payment proof and its approval: they go '
             'straight to Accounting to confirm the invoice.',
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('payment_proof_ids.state')
    def _compute_x_payment_proof(self):
        for order in self:
            states = set(order.payment_proof_ids.mapped('state'))
            order.x_has_payment_proof = bool(states)
            order.x_has_submitted_payment_proof = bool(
                states & {'submitted', 'approved'})
            if not states:
                status = 'none'
            elif 'rejected' in states:
                status = 'rejected'
            elif 'pending' in states:
                status = 'pending'
            elif 'submitted' in states:
                status = 'submitted'
            else:
                status = 'approved'
            order.x_payment_proof_status = status

    @api.depends('x_is_credit_payment_term', 'x_payment_proof_status',
                 'approval_state')
    def _compute_x_invoice_unlocked(self):
        for order in self:
            order.x_invoice_unlocked = (
                order.x_is_credit_payment_term
                or (order.x_payment_proof_status == 'approved'
                    and order.approval_state == 'approved'))

    @api.depends('payment_term_id', 'payment_term_id.name')
    def _compute_x_is_credit_payment_term(self):
        for order in self:
            term = order.payment_term_id
            order.x_is_credit_payment_term = bool(
                term and 'credit' in (term.name or '').lower())

    @api.depends_context('uid')
    def _compute_payment_proof_editable(self):
        user = self.env.user
        if user.has_group('base.group_system'):
            editable = True
        elif user.has_group(REVIEWER_GROUP):
            editable = False
        else:
            editable = user.has_group('sales_team.group_sale_salesman')
        for order in self:
            order.payment_proof_editable = editable

    @api.depends_context('uid')
    def _compute_can_create_invoice(self):
        user = self.env.user
        allowed = (
            user.has_group('sales_team.group_sale_salesman')
            or user.has_group(REVIEWER_GROUP)
            or user.has_group('base.group_system')
        )
        for order in self:
            order.can_create_invoice = allowed

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_submit_payment_proofs(self):
        """Submit every Pending / Rejected proof line of this order (used
        by the Submit button's auto-save flow, see proof_autosave.js)."""
        self.ensure_one()
        proofs = self.payment_proof_ids.filtered(
            lambda p: p.state in ('pending', 'rejected'))
        if not proofs:
            raise UserError(_(
                "There is no payment proof to submit. Add a line in the "
                "Payment Proofs tab and attach the files."))
        proofs.action_submit()
        return True

    def action_request_manager_approval(self):
        """Send the order to the High-Level Manager by hand. Normally this
        happens automatically when Accounting approves the payment proof;
        this button covers a manager rejection (resubmit after the issue
        is sorted out) and orders approved by Accounting before this step
        existed."""
        for order in self:
            if order.state != 'sale' or order.x_is_credit_payment_term:
                raise UserError(_(
                    "%s does not need the High-Level Manager's approval "
                    "at this stage.", order.name))
            if order.x_payment_proof_status != 'approved':
                raise UserError(_(
                    "%s: Accounting must approve the payment proof first.",
                    order.name))
            if order.approval_state == 'to_approve':
                raise UserError(_(
                    "%s is already waiting for the High-Level Manager.",
                    order.name))
            if order.approval_state == 'approved':
                raise UserError(_(
                    "%s was already approved by the High-Level Manager.",
                    order.name))
            order.sudo()._request_manager_after_payment()
        return True

    def _request_manager_after_payment(self):
        """Accounting approved the payment proof(s): send the order to the
        High-Level Manager and tell the salesperson it is on its way. The
        invoice stays locked (x_invoice_unlocked) until the manager
        approves. Not best-effort: if it fails (e.g. no manager
        configured) the caller's transaction rolls back, so an order can
        never be left approved by Accounting yet unknown to the manager."""
        for order in self:
            approved = order.payment_proof_ids.filtered(
                lambda p: p.state == 'approved')
            reviewer = (approved.sorted('reviewed_date')[-1:].reviewed_by
                        or self.env.user)
            order._request_manager_approval(previous_steps=[{
                'role': 'accounting',
                'user_id': reviewer.id,
                'status': 'approved',
                'date': fields.Datetime.now(),
                'note': _('Payment proof approved'),
            }])
            # A resubmission after a rejection closes the old To-Do.
            old = order.activity_ids.filtered(
                lambda a: a.summary == MANAGER_REJECTED_SUMMARY)
            if old:
                old.action_feedback(feedback=_("Sent to the manager again."))
            # Tell the salesperson (best effort).
            try:
                proof = self.env['sale.order.payment.proof']
                manager = order.high_level_manager_id
                for user in (order.user_id | order.payment_proof_ids.uploaded_by
                             ).filtered('active'):
                    proof._toast(
                        user, _('Sent for Manager Approval'),
                        _('%(order)s: payment approved by Accounting. It is '
                          'now with %(manager)s; you can create the invoice '
                          'once it is approved.', order=order.name,
                          manager=manager.name))
            except Exception:
                _logger.exception(
                    "accounting_so_invoice_bridge: could not notify Sales "
                    "that %s is with the manager.", order.name)

    def _notify_sales_invoice_ready(self):
        """Accounting AND the High-Level Manager approved: tell the
        salesperson the invoice can be created."""
        todo = self.env.ref('mail.mail_activity_data_todo',
                            raise_if_not_found=False)
        proof_model = self.env['sale.order.payment.proof']
        for order in self.sudo():
            if (not order.x_invoice_unlocked
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
                        note=_("Accounting approved the payment proof and "
                               "the High-Level Manager approved the order. "
                               "Press Create Invoice."))
                proof_model._toast(
                    user, _('Order Approved'),
                    _('%(order)s: approved by the manager. You can create '
                      'the invoice now.', order=order.name))

    def _after_manager_decision(self, decision, note=None):
        """Manager decided (hook of sale_credit_approval): approved ->
        the salesperson may create the invoice; rejected -> the
        salesperson (and Accounting) are told why."""
        res = super()._after_manager_decision(decision, note=note)
        proof_model = self.env['sale.order.payment.proof']
        todo = self.env.ref('mail.mail_activity_data_todo',
                            raise_if_not_found=False)
        for order in self.sudo():
            try:
                if decision == 'approved':
                    order._notify_sales_invoice_ready()
                elif decision == 'rejected':
                    users = (order.user_id
                             | order.payment_proof_ids.uploaded_by
                             ).filtered('active')
                    for user in users:
                        if todo:
                            order.activity_schedule(
                                'mail.mail_activity_data_todo',
                                user_id=user.id,
                                summary=MANAGER_REJECTED_SUMMARY,
                                note=_("The High-Level Manager rejected "
                                       "%(order)s%(reason)s. Sort it out, "
                                       "then press Send to Manager "
                                       "again.", order=order.name,
                                       reason=(": %s" % note) if note
                                       else ""))
                        proof_model._toast(
                            user, _('Order Rejected by Manager'),
                            _('%(order)s was rejected by the High-Level '
                              'Manager.', order=order.name))
                    # Accounting gets a note in the order chatter only.
                    order.message_post(
                        body=_("Manager rejection: Accounting and Sales "
                               "are informed."),
                        subtype_xmlid='mail.mt_note')
            except Exception:
                _logger.exception(
                    "accounting_so_invoice_bridge: manager-decision "
                    "notification for %s failed - the decision itself is "
                    "unaffected.", order.name)
        return res

    def action_view_payment_proofs(self):
        """Read-only popup of every proof on this order. Accountants open a
        row to Approve / Reject it."""
        self.ensure_one()
        list_view = self.env.ref(
            'accounting_so_invoice_bridge.view_sale_order_payment_proof_popup_list')
        form_view = self.env.ref(
            'accounting_so_invoice_bridge.view_sale_order_payment_proof_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment Proofs - %s', self.name),
            'res_model': 'sale.order.payment.proof',
            'view_mode': 'list,form',
            'views': [(list_view.id, 'list'), (form_view.id, 'form')],
            'domain': [('sale_order_id', '=', self.id)],
            'target': 'new',
        }

    def action_view_invoice(self, invoices=False):
        """Accountants / admins get Odoo's normal invoice page. Salespeople
        get a dedicated READ-ONLY page (no accounts, journal entries,
        balance or chatter): they see what the customer sees, nothing of
        the accounting. Used right after Create Invoice and by the
        Invoices smart button."""
        if self.env['sale.order.payment.proof']._is_reviewer():
            return super().action_view_invoice(invoices=invoices)
        invoices = invoices or self.mapped('invoice_ids')
        if not invoices:
            return {'type': 'ir.actions.act_window_close'}
        form = self.env.ref(
            'accounting_so_invoice_bridge.view_move_form_sales_readonly')
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'context': {'create': False},
        }
        if len(invoices) == 1:
            action.update(view_mode='form', views=[(form.id, 'form')],
                          res_id=invoices.id)
        else:
            lst = self.env.ref(
                'accounting_so_invoice_bridge.view_move_list_sales_readonly')
            action.update(view_mode='list,form',
                          views=[(lst.id, 'list'), (form.id, 'form')],
                          domain=[('id', 'in', invoices.ids)])
        return action

    def action_confirm(self):
        # Manager approval is gone, so make sure a quotation with an
        # unbalanced Selling Price (custom_sale_management) can't slip
        # through. Checked BEFORE super() writes anything.
        if hasattr(self, '_cim_check_balanced'):
            self._cim_check_balanced()
        return super().action_confirm()

    # ------------------------------------------------------------------
    # Invoicing
    # ------------------------------------------------------------------
    def _create_invoices(self, grouped=False, final=False, date=None):
        if not self.env.su:
            for order in self:
                if order.state == 'sale' and not order.x_invoice_unlocked:
                    if order.x_payment_proof_status == 'approved':
                        raise UserError(_(
                            "%(order)s cannot be invoiced yet: Accounting "
                            "approved the payment, but the High-Level "
                            "Manager has not approved the order (status: "
                            "%(status)s).",
                            order=order.name,
                            status=dict(self._fields['approval_state']
                                        ._description_selection(self.env))
                            .get(order.approval_state)))
                    raise UserError(_(
                        "%(order)s cannot be invoiced yet: Accounting has "
                        "not approved its payment proof (current status: "
                        "%(status)s). Submit the proof and wait for the "
                        "approval. Orders on a Credit payment term don't "
                        "need one.",
                        order=order.name,
                        status=dict(self._fields['x_payment_proof_status']
                                    ._description_selection(self.env))
                        .get(order.x_payment_proof_status)))
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        # The salesperson acted on the "approved" To-Do: close it.
        try:
            acts = self.sudo().activity_ids.filtered(
                lambda a: a.summary == INVOICE_READY_SUMMARY)
            if acts:
                acts.action_feedback(feedback=_("Invoice created."))
        except Exception:
            _logger.exception("accounting_so_invoice_bridge: could not close "
                              "the 'create invoice' activity.")
        # Second hand-off to Accounting: the draft invoice to confirm.
        # Best effort: a notification problem must never break invoicing.
        try:
            moves.filtered(lambda m: m.state == 'draft')\
                ._cim_notify_accounting_invoice_created()
        except Exception:
            _logger.exception(
                "accounting_so_invoice_bridge: could not notify Accounting "
                "about the new invoice(s) - invoice creation is unaffected.")
        return moves
