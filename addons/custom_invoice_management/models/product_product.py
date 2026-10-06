# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    cim_hide_from_invoice_lines = fields.Boolean(
        string="Hide From Invoice Lines Tab",
        help="When enabled, invoice lines using this product are hidden "
             "from the editable 'Invoice Lines' grid on Customer Invoices. "
             "They still fully count towards the invoice's totals and "
             "taxes, and remain fully visible on the 'Journal Items' tab "
             "and on the printed invoice.",
    )
