import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .sale_order_payment_proof import INVOICE_READY_SUMMARY

_logger = logging.getLogger(__name__)

REVIEWER_GROUP = 'accounting_so_invoice_bridge.group_sale_invoice_creator'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # The High-Level Manager approval (sale_credit_approval) is no longer
    # part of this flow: orders confirm directly. The approval machinery
    # stays installed, just not triggered by default.
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
             'order (Credit orders need no proof: always unlocked). The '
             'Create Invoice buttons and the server-side check use it.',
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

    @api.depends('x_is_credit_payment_term', 'x_payment_proof_status')
    def _compute_x_invoice_unlocked(self):
        for order in self:
            order.x_invoice_unlocked = (
                order.x_is_credit_payment_term
                or order.x_payment_proof_status == 'approved')

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
