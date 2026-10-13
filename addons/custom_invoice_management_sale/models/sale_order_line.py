# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Sales twin of the fields custom_invoice_management adds to
    # account.move.line.
    cim_hide_from_order_lines = fields.Boolean(
        related='product_id.cim_hide_from_invoice_lines',
        store=True,
        string="Hide From Order Lines Grid (technical)",
    )

    cim_selling_price = fields.Monetary(
        string="Selling Price",
        currency_field='currency_id',
        copy=False,
        help="The final, tax-included price agreed with the customer for "
             "this line. When the quotation is saved, this line's Other "
             "Income line is added/updated automatically so its total "
             "matches this amount exactly. VAT is applied automatically "
             "using the order's own VAT tax.",
    )

    # Technical: links a product line to the Other Income line that the
    # automatic balance generated for it, so balancing again updates the same
    # line instead of creating duplicates.
    cim_service_line_id = fields.Many2one(
        'sale.order.line',
        string="Generated Other Income Line (technical)",
        copy=False,
        ondelete='set null',
    )

    # Changing one of these on a line can change what it is worth, so the
    # order is balanced again.
    _CIM_REBALANCE_LINE_FIELDS = frozenset({
        'cim_selling_price', 'product_id', 'product_template_id', 'product_uom',
        'product_uom_qty', 'price_unit', 'discount', 'tax_id',
    })

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if (not self.env.context.get('cim_skip_auto_balance')
                and any(vals.get('cim_selling_price') for vals in vals_list)):
            lines.order_id._cim_auto_balance()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if (not self.env.context.get('cim_skip_auto_balance')
                and self._CIM_REBALANCE_LINE_FIELDS.intersection(vals)):
            self.order_id._cim_auto_balance()
        return res

    def unlink(self):
        # Deleting a balanced product line must also delete its generated
        # Other Income line, otherwise an invisible orphan line would keep
        # inflating the order total.
        service_lines = self.cim_service_line_id.exists() - self
        res = super().unlink()
        if service_lines:
            service_lines.unlink()
        return res

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        service_product = self.env.ref(
            'custom_invoice_management.product_service_charge', raise_if_not_found=False
        )
        if service_product and self.product_id == service_product and not self.display_type:
            # Same income account the invoice-side "Balance" button uses.
            account = self.company_id.cim_service_charge_account_id
            if account and 'account_id' not in optional_values:
                res['account_id'] = account.id
        return res
