from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    offline_page_title = fields.Char(
        string="Offline Page Title",
        config_parameter='web_offline_customize.title',
        help="Text shown instead of 'You are offline'. Leave empty to use the default.",
    )
    offline_page_message = fields.Text(
        string="Offline Page Message",
        help="Text shown instead of the default network connection message. "
             "Leave empty to use the default.",
    )
    offline_page_icon = fields.Binary(
        string="Offline Page Icon",
        help="Image shown instead of the default Odoo icon. Leave empty to use the default.",
    )
    offline_page_button_color = fields.Char(
        string="Offline Page Button Color",
        config_parameter='web_offline_customize.button_color',
        help="Hex color (e.g. #714B67) for the 'Check again' button. Leave empty to use the default.",
    )

    def set_values(self):
        super().set_values()
        icp = self.env['ir.config_parameter'].sudo()

        icp.set_param('web_offline_customize.message', self.offline_page_message or '')

        if self.offline_page_icon:
            icp.set_param(
                'web_offline_customize.icon',
                self.offline_page_icon.decode(),
            )
        else:
            icp.set_param('web_offline_customize.icon', '')

    @api.model
    def get_values(self):
        res = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()

        res['offline_page_message'] = icp.get_param('web_offline_customize.message', '')

        icon = icp.get_param('web_offline_customize.icon')
        res['offline_page_icon'] = icon.encode() if icon else False

        return res
