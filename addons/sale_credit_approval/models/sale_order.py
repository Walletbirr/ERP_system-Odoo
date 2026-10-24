# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    requires_credit_approval = fields.Boolean(
        string='Requires Manager Approval',
        default=True,
        store=True,
        help="Every Sales Order requires High-Level Manager approval before "
             "it can be confirmed, regardless of payment term.",
    )
    approval_state = fields.Selection(
        [
            ('not_required', 'Not Required'),
            ('to_approve', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Approval Status',
        default='not_required',
        copy=False,
        tracking=True,
    )
    approval_ids = fields.One2many(
        'sale.order.approval', 'sale_order_id', string='Approvals'
    )
    high_level_manager_id = fields.Many2one(
        'res.users', string='High-Level Manager',
        compute='_compute_high_level_manager_id',
    )
    can_approve_credit = fields.Boolean(
        string='Can Approve', compute='_compute_can_approve_credit',
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    # requires_credit_approval is intentionally NOT a compute field. It
    # used to be computed from payment_term_id.requires_manager_approval,
    # but the business rule is now a flat, unconditional "every order
    # requires approval" - a plain default is not just simpler, it's also
    # the correct fix for a real bug a computed version had: a stored
    # compute with an empty @api.depends() never runs for a brand-new,
    # not-yet-saved Quotation in the form view (only default_get() does),
    # so a fresh "New" order was showing the native Confirm button instead
    # of Request Approval until the very first save. A plain `default=True`
    # is filled in immediately, the same way Payment Terms already shows
    # "Immediate" the instant you open a new quotation.

    def _compute_high_level_manager_id(self):
        manager = self._get_configured_manager()
        for order in self:
            order.high_level_manager_id = manager

    def _compute_can_approve_credit(self):
        manager = self._get_configured_manager()
        is_admin = self.env.user.has_group('base.group_system')
        for order in self:
            order.can_approve_credit = (
                order.approval_state == 'to_approve'
                and bool(manager)
                and (self.env.user == manager or is_admin)
            )

    def _get_configured_manager(self):
        return self.env['bh.approval.config'].sudo().get_config().high_level_manager_id

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------
    def action_request_approval(self):
        """Send this order to the configured High-Level Manager for review
        (Sales-initiated path: only orders flagged requires_credit_approval)."""
        for order in self:
            if not order.requires_credit_approval:
                continue
            order._request_manager_approval(previous_steps=[{
                'role': 'sales',
                'user_id': order.user_id.id or self.env.user.id,
                'status': 'approved',
                'date': fields.Datetime.now(),
                'note': _('Submitted for approval'),
            }])

    def _request_manager_approval(self, previous_steps=None):
        """Put the order in front of the High-Level Manager.

        ``previous_steps`` are already-decided trail lines (a list of
        sale.order.approval vals) shown before the manager's pending line,
        e.g. the Sales submission, or Accounting's payment approval when
        the request comes from accounting_so_invoice_bridge.

        Does NOT check requires_credit_approval: callers decide when an
        order needs the manager.
        """
        manager = self._get_configured_manager()
        if not manager:
            raise UserError(_(
                "No High-Level Manager is configured for order approvals.\n"
                "Go to Executive Dashboard > Configuration > Approval "
                "Settings and set one first."
            ))
        for order in self:
            # Reset any previous pending step, keep history of decided ones
            order.approval_ids.filtered(lambda a: a.status == 'pending').unlink()
            steps = [(0, 0, dict(vals)) for vals in (previous_steps or [])]
            steps.append((0, 0, {
                'role': 'high_level_manager',
                'user_id': manager.id,
                'status': 'pending',
            }))
            order.write({
                'approval_state': 'to_approve',
                'approval_ids': steps,
            })

            order.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Approve Sales Order %s', order.name),
                note=_(
                    'Order %(order)s for %(customer)s needs your approval.',
                    order=order.name, customer=order.partner_id.name,
                ),
                user_id=manager.id,
            )
            order.message_post(
                body=_('Approval requested from %s for this order.', manager.name),
                partner_ids=manager.partner_id.ids,
            )

    def _after_manager_decision(self, decision, note=None):
        """Hook called after the manager approved ('approved') or rejected
        ('rejected') the order. Other modules extend it (e.g.
        accounting_so_invoice_bridge notifies the salesperson)."""
        return True

    def action_approve_credit_order(self, note=None):
        for order in self:
            if not order.can_approve_credit:
                raise UserError(_('You are not authorized to approve this order.'))
            order.approval_state = 'approved'
            approval = order.approval_ids.filtered(
                lambda a: a.role == 'high_level_manager' and a.status == 'pending'
            )
            vals = {'status': 'approved', 'date': fields.Datetime.now()}
            if note:
                vals['note'] = note
            approval.write(vals)

            activities = order.activity_ids.filtered(lambda a: a.user_id == self.env.user)
            if activities:
                activities.action_feedback(feedback=_('Approved by %s', self.env.user.name))
            order.message_post(body=_('Sales order approved by %s.', self.env.user.name))

            # Smart follow-through (approval BEFORE confirmation): once
            # approved there is nothing left for the salesperson to
            # decide, so confirm the order right away. Only for orders
            # that are not confirmed yet: when the approval comes AFTER
            # Accounting approved the payment, the order is already a
            # Sales Order and must NOT be confirmed a second time (that
            # would re-run delivery procurement).
            if order.state in ('draft', 'sent'):
                order.action_confirm()
            order._after_manager_decision('approved', note=note)

    def action_reject_credit_order(self, reason=None):
        for order in self:
            if not order.can_approve_credit:
                raise UserError(_('You are not authorized to reject this order.'))
            order.approval_state = 'rejected'
            approval = order.approval_ids.filtered(
                lambda a: a.role == 'high_level_manager' and a.status == 'pending'
            )
            vals = {'status': 'rejected', 'date': fields.Datetime.now()}
            if reason:
                vals['note'] = reason
            approval.write(vals)

            activities = order.activity_ids.filtered(lambda a: a.user_id == self.env.user)
            if activities:
                activities.action_feedback(feedback=_('Rejected by %s', self.env.user.name))
            order.message_post(body=_('Sales order rejected by %s.', self.env.user.name))
            order._after_manager_decision('rejected', note=reason)

    # ------------------------------------------------------------------
    # Confirm override
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Guard confirmation for orders that require credit approval.

        IMPORTANT: this method must never perform real writes (via
        action_request_approval) and then raise an exception in the same
        call. A single button click is a single DB transaction in Odoo —
        raising after writing rolls the whole transaction back, silently
        discarding the approval request, the chatter message and the
        manager's activity. That was the root cause of the "Not Required"
        / empty "Pending My Approval" bug: nothing was ever actually saved.

        So: if nothing needs to be written, it's safe to raise (blocking,
        informational). If something *does* need to be written
        (action_request_approval), we must return normally so the
        transaction commits, and use a client notification instead of an
        exception to inform the user.
        """
        blocking_orders = self.filtered(
            lambda o: o.requires_credit_approval and o.approval_state == 'to_approve'
        )
        if blocking_orders:
            # Nothing written in this branch - safe to raise.
            order = blocking_orders[0]
            raise UserError(_(
                'Sales Order %(order)s is still waiting for approval from '
                '%(manager)s. It cannot be confirmed yet.',
                order=order.name,
                manager=order.high_level_manager_id.name or _('the High-Level Manager'),
            ))

        # 'rejected' or 'not_required'-yet-flagged orders: (re)send for
        # approval. A previously rejected order is resubmitted rather than
        # blocked forever.
        to_request = self.filtered(
            lambda o: o.requires_credit_approval and o.approval_state != 'approved'
        )
        to_confirm = self - to_request

        result = True
        if to_confirm:
            result = super(SaleOrder, to_confirm).action_confirm()

        if to_request:
            to_request.action_request_approval()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Approval requested'),
                    'message': _(
                        'Sent for High-Level Manager approval: %s. You will '
                        'be able to confirm once approved.'
                    ) % ', '.join(to_request.mapped('name')),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        return result
