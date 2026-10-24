# -*- coding: utf-8 -*-
"""Lets the Executive Dashboard mobile app read the payment slip of an order.

Same authentication as the other /bh_dashboard/mobile/* routes: the
"API-KEY" header, and the caller must be an Executive (or Settings admin).
Only the payment proof file is served - NOT the client's ID document.
"""
import logging
import mimetypes

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Refuse anything bigger (the phone would struggle and the JSON-RPC
# envelope carries the file as base64, ~33% larger).
MAX_FILE_BYTES = 12 * 1024 * 1024


class BhDashboardMobileProofs(http.Controller):

    def _api_key_uid(self):
        api_key = request.httprequest.headers.get('API-KEY')
        if not api_key:
            return None
        try:
            return request.env['res.users.apikeys']._check_credentials(
                scope='rpc', key=api_key)
        except Exception:
            return None

    @http.route('/bh_dashboard/mobile/approvals/proof_file', type='json',
                auth='public', csrf=False, methods=['POST'])
    def mobile_proof_file(self, proof_id=None, **kwargs):
        uid = self._api_key_uid()
        if not uid:
            return {'error': 'invalid_api_key'}
        user = request.env['res.users'].sudo().browse(uid)
        if not (user.has_group('bh_management_dashboard.group_bh_executive')
                or user.has_group('base.group_system')):
            return {'error': 'access_denied'}

        try:
            proof_id = int(proof_id)
        except (TypeError, ValueError):
            return {'error': 'missing_proof_id',
                    'message': 'The payment proof could not be identified.'}

        proof = request.env['sale.order.payment.proof'].sudo().browse(
            proof_id).exists()
        attachment = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'sale.order.payment.proof'),
            ('res_field', '=', 'proof_file'),
            ('res_id', '=', proof.id or 0),
        ], limit=1)
        if not proof or not attachment:
            return {'error': 'proof_not_found',
                    'message': 'No payment slip is attached to this order.'}
        if attachment.file_size > MAX_FILE_BYTES:
            return {'error': 'proof_too_large',
                    'message': 'The payment slip is too large to open on '
                               'the phone. Open it from Odoo instead.'}

        filename = proof.proof_filename or 'payment_proof'
        data = proof.proof_file
        if isinstance(data, bytes):
            data = data.decode()
        return {
            'filename': filename,
            'mimetype': (attachment.mimetype
                         or mimetypes.guess_type(filename)[0]
                         or 'application/octet-stream'),
            'data': data,  # base64
        }