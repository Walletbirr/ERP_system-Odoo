# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    careers_portal_color = fields.Char(
        string='Careers Portal Accent Color',
        default='#714B67',
        help='Hex color code (e.g. #1A73E8) used for buttons and accents '
             'on the public Careers Portal (/careers). The company logo '
             'is also shown there automatically.',
    )
