# -*- coding: utf-8 -*-
from odoo import api, fields, models


def _cim_is_wht_tax(tax):
    # Local copy of account_move.cim_is_wht_tax (avoids a circular import).
    return tax.amount_type == 'percent' and (tax.amount or 0.0) < 0


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
        compute='_compute_cim_selling_price',
        store=True,
        readonly=False,
        copy=False,
        help="The final, tax-included price agreed with the customer for "
             "this line. It is filled in automatically with the line's "
             "tax-included total (VAT / Excise included) and follows the "
             "line while you do not touch it. Type a higher amount and it "
             "becomes your own price: this line's Service Charge line is "
             "then added/updated automatically when the invoice is saved "
             "so the total matches this amount exactly.",
    )

    # Technical: the Selling Price the system filled in last time. While the
    # Selling Price still equals it, the user has not typed their own price,
    # so it keeps following the line; once they differ, the typed price wins.
    cim_auto_selling_price = fields.Monetary(
        string="Automatic Selling Price (technical)",
        currency_field='currency_id',
        compute='_compute_cim_selling_price',
        store=True,
        readonly=False,
        copy=False,
    )

    # Technical: links a product line to the Service Charge line that the
    # automatic balance generated for it, so balancing again updates the
    # same line instead of creating duplicates.
    cim_service_line_id = fields.Many2one(
        'account.move.line',
        string="Generated Service Charge Line (technical)",
        copy=False,
        ondelete='set null',
    )

    # Changing one of these on a line can change what it is worth, so the
    # invoice is balanced again.
    _CIM_REBALANCE_LINE_FIELDS = frozenset({
        'cim_selling_price', 'product_id', 'product_uom_id', 'quantity',
        'price_unit', 'discount', 'tax_ids',
    })

    # ------------------------------------------------------------------
    # Automatic Selling Price
    # ------------------------------------------------------------------
    def _cim_service_product(self):
        return self.env.ref(
            'custom_invoice_management.product_service_charge',
            raise_if_not_found=False)

    def _cim_auto_price_applies(self):
        """Real product lines of customer invoices / credit notes only:
        never section / note lines, down payments or the generated Service
        Charge lines."""
        self.ensure_one()
        service_product = self._cim_service_product()
        return bool(
            self.display_type == 'product'
            and self.product_id
            and self.product_id != service_product
            and not ('is_downpayment' in self._fields and self.is_downpayment)
            and not self.cim_hide_from_invoice_lines
            and self.move_id.move_type in ('out_invoice', 'out_refund')
        )

    def _cim_line_total_before_wht(self):
        """Tax-included total of the line (VAT / Excise included,
        withholding tax left out): exactly the amount balancing compares the
        Selling Price with, so the automatic price never needs a Service
        Charge line and can never be 'lower than the line'."""
        self.ensure_one()
        taxes = self.tax_ids.filtered(lambda t: not _cim_is_wht_tax(t))
        currency = self.currency_id or self.move_id.currency_id
        total = taxes.compute_all(
            self.price_unit * (1 - (self.discount or 0.0) / 100.0),
            currency=currency,
            quantity=self.quantity,
            product=self.product_id,
            partner=self.move_id.partner_id,
            is_refund=self.move_id.move_type == 'out_refund',
        )['total_included']
        return currency.round(total) if currency else total

    @api.depends('product_id', 'quantity', 'price_unit', 'discount', 'tax_ids')
    def _compute_cim_selling_price(self):
        for line in self:
            current = line.cim_selling_price
            current_auto = line.cim_auto_selling_price
            # Posted / cancelled documents are history: leave them alone.
            if line.move_id.state not in (False, 'draft'):
                line.cim_selling_price = current
                line.cim_auto_selling_price = current_auto
                continue
            if not line._cim_auto_price_applies():
                line.cim_selling_price = 0.0
                line.cim_auto_selling_price = 0.0
                continue
            auto = line._cim_line_total_before_wht()
            currency = line.currency_id or line.move_id.currency_id
            # Empty, or still the price we filled in: follow the line.
            # Anything else was typed by the user: keep it.
            follows = not current or (
                currency.compare_amounts(current, current_auto) == 0
                if currency else current == current_auto)
            if follows:
                line.cim_selling_price = auto
            else:
                line.cim_selling_price = current
            line.cim_auto_selling_price = auto

    # ------------------------------------------------------------------
    # Automatic balance hooks
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if (not self.env.context.get('cim_skip_auto_balance')
                and any(vals.get('cim_selling_price') for vals in vals_list)):
            lines.move_id._cim_auto_balance()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if (not self.env.context.get('cim_skip_auto_balance')
                and self._CIM_REBALANCE_LINE_FIELDS.intersection(vals)):
            self.move_id._cim_auto_balance()
        return res

    def unlink(self):
        # Deleting a balanced product line must also delete its generated
        # Service Charge line, otherwise an invisible orphan line would keep
        # inflating the invoice total.
        service_lines = self.cim_service_line_id.exists() - self
        res = super().unlink()
        if service_lines:
            service_lines.unlink()
        return res
