# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    cim_hide_from_invoice_lines = fields.Boolean(
        related='product_id.cim_hide_from_invoice_lines',
        store=True,
        string="Hide From Invoice Lines Tab (technical)",
    )

    cim_selling_price = fields.Monetary(
        string="Selling Price",
        currency_field='currency_id',
        copy=False,
        help="The final, tax-included price agreed with the customer for "
             "this line (e.g. the amount written on the official sales "
             "voucher). Click \"Balance\" to auto-add/update this line's "
             "Service Charge line so its total matches this amount "
             "exactly. VAT is applied automatically using the invoice's "
             "own VAT tax - no need to pick one per line.",
    )

    # Technical: links a product line to the Service Charge line that
    # "Balance" generated for it, so re-clicking "Balance" updates the
    # same line instead of creating duplicates.
    cim_service_line_id = fields.Many2one(
        'account.move.line',
        string="Generated Service Charge Line (technical)",
        copy=False,
        ondelete='set null',
    )

