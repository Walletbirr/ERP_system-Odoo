import base64

from odoo import http
from odoo.http import request
from odoo.tools import file_open

from odoo.addons.web.controllers.webmanifest import WebManifest as WebManifestController


class WebManifest(WebManifestController):

    @http.route('/odoo/offline', type='http', auth='public', methods=['GET'], readonly=True)
    def offline(self):
        """ Returns the offline page delivered by the service worker,
        injecting custom branding (title, message, icon) if configured
        in Settings > General Settings > Offline Page.
        """
        icp = request.env['ir.config_parameter'].sudo()
        custom_icon = icp.get_param('web_offline_customize.icon', False)
        custom_title = icp.get_param('web_offline_customize.title', False)
        custom_message = icp.get_param('web_offline_customize.message', False)
        custom_button_color = icp.get_param('web_offline_customize.button_color', False)

        values = {
            'odoo_icon': base64.b64encode(file_open(self._icon_path(), 'rb').read()),
            'custom_icon': custom_icon or False,
            'custom_title': custom_title or False,
            'custom_message': custom_message or False,
            'custom_button_color': custom_button_color or False,
        }
        return request.render('web.webclient_offline', values)
