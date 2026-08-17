# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request


class TestWatermarkController(http.Controller):

    @http.route('/test_watermark/get_config', type='http', auth='public', methods=['GET'], csrf=False)
    def get_config(self, **kwargs):
        icp = request.env['ir.config_parameter'].sudo()
        config = {
            'enabled': icp.get_param('test_watermark.enabled', 'True') == 'True',
            'text': icp.get_param('test_watermark.text', 'TEST'),
            'color': icp.get_param('test_watermark.color', '#FF0000'),
            'opacity': float(icp.get_param('test_watermark.opacity', '0.12') or 0.12),
        }
        return request.make_response(
            json.dumps(config),
            headers=[('Content-Type', 'application/json')],
        )
