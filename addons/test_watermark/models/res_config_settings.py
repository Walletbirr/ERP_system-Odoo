# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    test_watermark_enabled = fields.Boolean(
        string="Show Watermark",
        config_parameter='test_watermark.enabled',
        default=True,
        help="Display a repeating watermark overlay across the whole system.",
    )
    test_watermark_text = fields.Char(
        string="Watermark Text",
        config_parameter='test_watermark.text',
        default="TEST",
    )
    test_watermark_color = fields.Char(
        string="Watermark Color",
        config_parameter='test_watermark.color',
        default="#FF0000",
        help="Hex color code, e.g. #FF0000",
    )
    test_watermark_opacity = fields.Float(
        string="Watermark Opacity",
        config_parameter='test_watermark.opacity',
        default=0.12,
        help="Value between 0 (invisible) and 1 (fully opaque). Recommended: 0.08 - 0.20",
    )
