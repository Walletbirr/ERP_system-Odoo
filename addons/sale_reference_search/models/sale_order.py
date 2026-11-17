# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Make the Reference searchable from anywhere the order is looked up by
    # name (Many2one dropdowns, the default search box, global search...).
    # We extend the list of the standard module instead of replacing it.
    @property
    def _rec_names_search(self):
        return list(dict.fromkeys(
            list(super()._rec_names_search or ['name']) + ['cim_reference']
        ))
