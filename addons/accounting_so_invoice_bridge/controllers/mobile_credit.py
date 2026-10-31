# -*- coding: utf-8 -*-
"""Customer credit history for the Executive Dashboard mobile app.

Same authentication as the other /bh_dashboard/mobile/* routes: the
"API-KEY" header, and the caller must be an Executive (or Settings admin).
The data comes from customer_credit_report (customer.credit.api).
"""
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class BhDashboardMobileCredit(http.Controller):

    def _executive_uid(self):
        api_key = request.httprequest.headers.get('API-KEY')
        if not api_key:
            return None, {'error': 'invalid_api_key'}
        try:
            uid = request.env['res.users.apikeys']._check_credentials(
                scope='rpc', key=api_key)
        except Exception:
            uid = None
        if not uid:
            return None, {'error': 'invalid_api_key'}
        user = request.env['res.users'].sudo().browse(uid)
        if not (user.has_group('bh_management_dashboard.group_bh_executive')
                or user.has_group('base.group_system')):
            return None, {'error': 'access_denied'}
        return uid, None

    @http.route('/bh_dashboard/mobile/credit/customer', type='json',
                auth='public', csrf=False, methods=['POST'])
    def mobile_credit_customer(self, partner_id=None, **kwargs):
        uid, error = self._executive_uid()
        if error:
            return error
        try:
            partner_id = int(partner_id)
        except (TypeError, ValueError):
            return {'error': 'missing_partner_id',
                    'message': 'The customer could not be identified.'}
        env = request.env(user=uid)
        partner = env['res.partner'].sudo().browse(partner_id).exists()
        if not partner:
            return {'error': 'partner_not_found',
                    'message': 'This customer no longer exists.'}
        try:
            return env['customer.credit.api'].customer_history(
                partner, env.user.company_id)
        except Exception:
            _logger.exception("mobile credit history failed for partner %s",
                              partner_id)
            return {'error': 'action_failed',
                    'message': 'Could not load the credit history.'}
