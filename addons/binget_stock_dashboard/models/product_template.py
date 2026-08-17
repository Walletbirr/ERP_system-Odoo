# -*- coding: utf-8 -*-
# Favorites use product.template.is_favorite (standard in Odoo 18).
# Kept as a lightweight inherit hook for future extensions.
from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"
