# -*- coding: utf-8 -*-
from odoo import api, fields, models

from odoo.addons.custom_invoice_management.models.account_move import cim_is_wht_tax


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
        compute='_compute_cim_selling_price',
        store=True,
        readonly=False,
        copy=False,
        help="The final, tax-included price agreed with the customer for "
             "this line. It is filled in automatically with the line's "
             "tax-included total (unit price x quantity, with the line's "
             "VAT, 15% here) and follows the line while you do not touch "
             "it. Type another amount (higher than the line total) and it "
             "becomes your own price: this line's Other Income line is "
             "then added/updated automatically when the quotation is "
             "saved so the total matches this amount exactly.",
    )

    # Technical: the Selling Price the system filled in last time. While the
    # Selling Price still equals it the user has not typed their own price,
    # so it keeps following the line; once they differ the typed price wins
    # and is kept (this is what lets the Other Income line absorb a unit
    # price change).
    cim_auto_selling_price = fields.Monetary(
        string="Automatic Selling Price (technical)",
        currency_field='currency_id',
        compute='_compute_cim_selling_price',
        store=True,
        readonly=False,
        copy=False,
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

    # ------------------------------------------------------------------
    # Automatic Selling Price
    # ------------------------------------------------------------------
    def _cim_auto_price_applies(self):
        """Real product lines only: never section / note lines, down
        payments or the generated Other Income lines."""
        self.ensure_one()
        service_product = self.env.ref(
            'custom_invoice_management.product_service_charge',
            raise_if_not_found=False)
        return bool(
            not self.display_type
            and self.product_id
            and self.product_id != service_product
            and not self.is_downpayment
            and not self.cim_hide_from_order_lines
        )

    def _cim_line_total_before_wht(self):
        """Tax-included total of the line (VAT / Excise included,
        withholding tax left out): exactly the amount _cim_balance compares
        the Selling Price with, so the automatic price never needs an Other
        Income line and can never be 'lower than the line'."""
        self.ensure_one()
        taxes = self.tax_id.filtered(lambda t: not cim_is_wht_tax(t))
        currency = (self.currency_id or self.order_id.currency_id
                    or self.company_id.currency_id)
        total = taxes.compute_all(
            self.price_unit * (1 - (self.discount or 0.0) / 100.0),
            currency=currency,
            quantity=self.product_uom_qty,
            product=self.product_id,
            partner=self.order_id.partner_id,
        )['total_included']
        return currency.round(total) if currency else total

    @api.depends('product_id', 'product_uom_qty', 'price_unit', 'discount',
                 'tax_id')
    def _compute_cim_selling_price(self):
        for line in self:
            if not line._cim_auto_price_applies():
                line.cim_selling_price = 0.0
                line.cim_auto_selling_price = 0.0
                continue
            auto = line._cim_line_total_before_wht()
            current = line.cim_selling_price
            currency = line.currency_id or line.order_id.currency_id
            # Empty, or still the price we filled in: follow the line.
            # Anything else was typed by the user: keep it.
            follows = not current or (
                currency.compare_amounts(
                    current, line.cim_auto_selling_price) == 0
                if currency else current == line.cim_auto_selling_price)
            if follows:
                line.cim_selling_price = auto
            line.cim_auto_selling_price = auto

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
