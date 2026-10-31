# -*- coding: utf-8 -*-
"""Push notification to the High-Level Manager's phone.

When an order is put in front of the manager (_request_manager_approval),
ask the mobile app's BFF to send a push. Odoo knows nothing about Expo or
device tokens: it only tells the BFF WHICH USER (res.users id) to notify and
WHAT to say. The BFF owns the device tokens.

Configuration (Settings > Technical > System Parameters):
    bh_push.bff_url   Base URL of the BFF as seen from Odoo,
                      e.g. http://localhost:4000 (default).
    bh_push.secret    Same value as PUSH_WEBHOOK_SECRET in the BFF's .env.
                      Without it nothing is sent (the feature is off).

Never blocks or breaks the approval: the request is sent after the database
commit, from a background thread, and every failure is only logged.
"""
import logging
import threading

import requests

from odoo import models

_logger = logging.getLogger(__name__)

PUSH_TIMEOUT = 5  # seconds


def _post_to_bff(url, secret, payload):
    try:
        response = requests.post(
            url, json=payload, headers={'X-Push-Secret': secret},
            timeout=PUSH_TIMEOUT)
        if response.status_code >= 400:
            _logger.warning(
                "bh_push: BFF answered HTTP %s for order %s",
                response.status_code, payload.get('data', {}).get('order_name'))
    except Exception:  # never let a notification problem leak anywhere
        _logger.exception("bh_push: could not reach the BFF at %s", url)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _request_manager_approval(self, previous_steps=None):
        res = super()._request_manager_approval(previous_steps=previous_steps)
        try:
            self._bh_push_manager_request()
        except Exception:
            _logger.exception("bh_push: could not prepare the push")
        return res

    def _bh_push_manager_request(self):
        params = self.env['ir.config_parameter'].sudo()
        secret = params.get_param('bh_push.secret')
        if not secret:
            return
        base_url = (params.get_param('bh_push.bff_url')
                    or 'http://localhost:4000').rstrip('/')
        manager = self._get_configured_manager()
        if not manager:
            return
        # The number the app shows on its icon: what is waiting for a
        # decision right now (this order is already counted: it was just
        # written as 'to_approve').
        pending = self.env['sale.order'].sudo().search_count(
            [('approval_state', '=', 'to_approve')])

        payloads = []
        for order in self.sudo():
            payloads.append({
                'uids': [manager.id],
                'title': ('Credit approval needed'
                          if getattr(order, 'x_sale_type', False) == 'credit'
                          else 'Approval needed'),
                'body': '%s - %s - %s %s' % (
                    order.name, order.partner_id.name or '',
                    order.currency_id.symbol or order.currency_id.name or '',
                    '{:,.2f}'.format(order.amount_total)),
                'badge': pending,
                'data': {
                    'type': 'order_approval',
                    'order_id': order.id,
                    'order_name': order.name,
                },
            })
        if not payloads:
            return

        url = base_url + '/internal/push/notify'

        def _send():
            # Runs after COMMIT: the manager can never be told about an
            # order whose approval request was rolled back. A thread keeps
            # the salesperson's / accountant's click from waiting on it.
            for payload in payloads:
                threading.Thread(
                    target=_post_to_bff, args=(url, secret, payload),
                    daemon=True).start()

        self.env.cr.postcommit.add(_send)
