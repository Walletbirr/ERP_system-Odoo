# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.bh_management_dashboard.controllers.bh_dashboard_controller import (
    BhDashboardController,
)

_logger = logging.getLogger(__name__)


class BhDashboardMobileApprovalsController(BhDashboardController):
    """Mobile Approve/Reject actions for the Credit Approval workflow.

    Defined here (in sale_credit_approval), not in bh_management_dashboard,
    to keep the one-way dependency intact - sale_credit_approval already
    depends on bh_management_dashboard, so subclassing its controller just
    to reuse `_authenticate_api_key` / `_check_executive_access` (the same
    API-KEY auth pattern as every other /mobile/* route) is safe; the base
    module still has zero awareness of this one.

    Passing `_check_executive_access` only confirms the user may see the
    dashboard. Whether they may act on THIS specific order is enforced
    separately by `sale.order.can_approve_credit`, the same guard the web
    form's Approve/Reject buttons use - so a manager can only decide orders
    routed to them (or an admin, for either).
    """

    def _mobile_decide(self, order_id, decision, note=None):
        uid = self._authenticate_api_key()
        if not uid:
            return {'error': 'invalid_api_key'}
        if not self._check_executive_access(uid):
            return {'error': 'access_denied'}
        if not order_id:
            return {'error': 'missing_order_id'}

        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            return {'error': 'missing_order_id'}

        order = request.env['sale.order'].with_user(uid).browse(order_id)
        if not order.exists():
            return {'error': 'order_not_found'}

        try:
            if decision == 'approve':
                order.action_approve_credit_order(note=note)
            else:
                order.action_reject_credit_order(reason=note)
        except UserError as e:
            # e.g. "not your order to decide" / already decided by someone
            # else since this manager's list was last fetched.
            return {'error': 'not_authorized', 'message': str(e)}
        except Exception:
            _logger.exception(
                'BH Dashboard mobile: failed to %s order %s', decision, order_id
            )
            return {'error': 'action_failed'}

        return {
            'success': True,
            'order_id': order.id,
            'name': order.name,
            'approval_state': order.approval_state,
        }

    @http.route('/bh_dashboard/mobile/approvals/approve', type='json', auth='public', csrf=False, methods=['POST'])
    def mobile_approve_credit_order(self, order_id=None, note=None, **kwargs):
        return self._mobile_decide(order_id, 'approve', note=note)

    @http.route('/bh_dashboard/mobile/approvals/reject', type='json', auth='public', csrf=False, methods=['POST'])
    def mobile_reject_credit_order(self, order_id=None, reason=None, **kwargs):
        return self._mobile_decide(order_id, 'reject', note=reason)
