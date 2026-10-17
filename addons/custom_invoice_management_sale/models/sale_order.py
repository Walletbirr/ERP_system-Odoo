# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from odoo.addons.custom_invoice_management.models.account_move import cim_is_wht_tax


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Free-text Reference of the order. It travels with the order through the
    # whole process: it is copied onto every invoice generated from it (see
    # _prepare_invoice) and from there onto credit notes.
    cim_reference = fields.Char(
        string="Reference",
        copy=False,
        tracking=True,
        help="Free-text reference of this order. It is carried over "
             "automatically to the invoice(s) generated from the order.",
    )

    # ------------------------------------------------------------------
    # Display-only totals box (same fields / meaning as on the invoice).
    # The real accounting (amount_total, tax_totals, the invoice that is
    # generated, the printed quotation) is untouched.
    # ------------------------------------------------------------------
    cim_product_untaxed_amount = fields.Monetary(
        string="Untaxed Amount",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Untaxed Amount of the product line(s) only - excludes the "
             "auto-generated Other Income line(s).",
    )
    cim_excise_tax_amount = fields.Monetary(
        string="Excise Tax",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Total of any tax that affects the base of subsequent taxes "
             "(e.g. Excise Tax).",
    )
    cim_subtotal_before_vat = fields.Monetary(
        string="Subtotal",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Untaxed Amount (product line(s) only) plus Excise Tax.",
    )
    cim_service_charge_amount = fields.Monetary(
        string="Other Income",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Untaxed total of the auto-generated Other Income line(s).",
    )
    cim_before_vat_amount = fields.Monetary(
        string="Before Vat",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Subtotal plus Other Income - the full taxable base that VAT "
             "is then computed on.",
    )
    cim_vat_amount = fields.Monetary(
        string="Vat",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Total VAT (tax other than Excise Tax and Withholding Tax).",
    )
    cim_wht_amount = fields.Monetary(
        string="Withholding Tax",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Total withholding tax (shown as a negative amount: it is "
             "deducted from what the customer pays).",
    )
    cim_total_before_wht = fields.Monetary(
        string="Total Before WHT",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Total including VAT / Excise but before the withholding tax "
             "deduction.",
    )

    @api.depends(
        'currency_id',
        'amount_untaxed',
        'amount_tax',
        'amount_total',
        'order_line.product_id',
        'order_line.tax_id',
        'order_line.price_unit',
        'order_line.discount',
        'order_line.product_uom_qty',
        'order_line.price_subtotal',
        'order_line.price_tax',
        'order_line.price_total',
    )
    def _compute_cim_totals(self):
        service_product = self.env.ref(
            'custom_invoice_management.product_service_charge', raise_if_not_found=False
        )
        Tax = self.env['account.tax']
        for order in self:
            currency = order.currency_id or order.company_id.currency_id
            excise_amount = 0.0
            wht_amount = 0.0
            service_charge_amount = 0.0

            for line in order.order_line.filtered(lambda l: not l.display_type):
                if service_product and line.product_id == service_product:
                    service_charge_amount += line.price_subtotal
                if not line.tax_id:
                    continue
                # Split the line's tax into Excise (affects base of the
                # following taxes), Withholding (negative %) and the rest
                # (VAT), the same split the invoice box does from tax lines.
                details = line.tax_id.compute_all(
                    line.price_unit * (1.0 - (line.discount or 0.0) / 100.0),
                    currency=currency,
                    quantity=line.product_uom_qty,
                    product=line.product_id,
                    partner=order.partner_id,
                )
                for tax_detail in details['taxes']:
                    tax = Tax.browse(tax_detail['id'])
                    if cim_is_wht_tax(tax):
                        wht_amount += tax_detail['amount']
                    elif tax.include_base_amount:
                        excise_amount += tax_detail['amount']

            order.cim_service_charge_amount = service_charge_amount
            order.cim_excise_tax_amount = excise_amount
            order.cim_wht_amount = wht_amount
            order.cim_total_before_wht = order.amount_total - wht_amount
            order.cim_vat_amount = order.amount_tax - excise_amount - wht_amount
            order.cim_product_untaxed_amount = order.amount_untaxed - service_charge_amount
            order.cim_subtotal_before_vat = order.cim_product_untaxed_amount + excise_amount
            order.cim_before_vat_amount = order.cim_subtotal_before_vat + service_charge_amount

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------
    @api.model
    def _cim_get_service_charge_product(self):
        return self.env['account.move']._cim_get_service_charge_product()

    def _cim_get_common_vat_tax(self, candidate_lines):
        """The single VAT tax to charge on every Other Income line of this
        order: the first non-Excise sale tax found on the order's own product
        lines (Excise = a tax with "Affect Base of Subsequent Taxes")."""
        self.ensure_one()
        for line in candidate_lines:
            vat_taxes = line.tax_id.filtered(
                lambda t: t.type_tax_use == 'sale'
                and not t.include_base_amount
                and not cim_is_wht_tax(t)
            )
            if vat_taxes:
                return vat_taxes[0]
        return self.env['account.tax']

    # Fields of the order whose change can alter what a line is worth, so the
    # Other Income lines have to be re-balanced when they are written.
    _CIM_REBALANCE_ORDER_FIELDS = frozenset({
        'order_line', 'pricelist_id', 'fiscal_position_id', 'partner_id', 'currency_id',
    })

    def write(self, vals):
        if (self.env.context.get('cim_skip_auto_balance')
                or not self._CIM_REBALANCE_ORDER_FIELDS.intersection(vals)):
            return super().write(vals)
        # Let the whole write finish first (lines included), then balance once.
        res = super(SaleOrder, self.with_context(cim_skip_auto_balance=True)).write(vals)
        self._cim_auto_balance()
        return res

    def _cim_check_selling_price_before_confirm(self):
        """Every product line needs a Selling Price before the order can be
        confirmed (it is what drives the Other Income line / the total)."""
        service_product = self.env.ref(
            'custom_invoice_management.product_service_charge', raise_if_not_found=False
        )
        for order in self.filtered(lambda o: o.state in ('draft', 'sent')):
            missing = order.order_line.filtered(
                lambda l: not l.display_type
                and l.product_id
                and l.product_id != service_product
                and not l.is_downpayment
                and not l.cim_selling_price
            )
            if missing:
                raise UserError(_(
                    "A Selling Price is required on every order line before "
                    "the order can be confirmed.\n\n"
                    "Missing on:\n%(lines)s\n\n"
                    "Enter it in the Selling Price column and save.",
                    lines="\n".join(
                        "- %s" % (l.product_id.display_name or l.name) for l in missing
                    ),
                ))

    def action_confirm(self):
        self._cim_check_selling_price_before_confirm()
        return super().action_confirm()

    def action_cim_balance(self):
        """Balance this order on demand.

        The order is balanced automatically every time it is saved (see
        ``_cim_auto_balance``), so the form no longer has a Balance button.
        This method stays available for server actions / scripts and, unlike
        the automatic run, complains when no line has a Selling Price.
        """
        self.ensure_one()

        if self.state not in ('draft', 'sent'):
            raise UserError(_(
                "Balancing is only possible on quotations. Set this order "
                "back to quotation before balancing."
            ))

        self._cim_balance(strict=True)
        return True

    def _cim_auto_balance(self):
        """Silent balance run on save. Only quotations are touched and an
        order without any Selling Price is simply left alone."""
        for order in self:
            if order.state in ('draft', 'sent'):
                order._cim_balance(strict=False)

    def _cim_balance(self, strict=False):
        """For every order line where a "Selling Price" (tax incl.) has been
        entered, add/update an Other Income line - taxed at the order's common
        VAT tax - so that the line's own price_total plus its Other Income
        line equals the negotiated Selling Price.

        Mirrors account.move.action_cim_balance one-to-one.

        :param strict: raise when no line has a Selling Price (what the old
            "Balance" button did) instead of quietly doing nothing.
        """
        self.ensure_one()
        # Everything written below must not trigger another balance run.
        order = self.with_context(cim_skip_auto_balance=True)

        service_product = order._cim_get_service_charge_product()

        # Real product lines only - the Other Income lines this action
        # itself generates (and down payments) are never balanced.
        candidate_lines = order.order_line.filtered(
            lambda l: not l.display_type
            and l.product_id
            and l.product_id != service_product
            and not l.is_downpayment
        )

        # Lines whose target was cleared: drop their old Other Income line.
        cleared_lines = candidate_lines.filtered(
            lambda l: not l.cim_selling_price and l.cim_service_line_id
        )
        for line in cleared_lines:
            service_line = line.cim_service_line_id
            line.cim_service_line_id = False
            service_line.unlink()

        lines_to_balance = candidate_lines.filtered(lambda l: l.cim_selling_price)
        if not lines_to_balance:
            if strict:
                raise UserError(_(
                    "Please enter a Selling Price on at least one order "
                    "line before balancing."
                ))
            return

        vat_tax = order._cim_get_common_vat_tax(candidate_lines)
        currency = order.currency_id

        for line in lines_to_balance:
            # The Selling Price is the VAT/Excise-inclusive price agreed with
            # the customer. Withholding tax is a deduction on top of it, so it
            # must not count towards the line's own total here.
            wht_taxes = line.tax_id.filtered(cim_is_wht_tax)
            if wht_taxes:
                net_taxes = line.tax_id - wht_taxes
                base_total = net_taxes.compute_all(
                    line.price_unit * (1 - (line.discount or 0.0) / 100.0),
                    currency=currency,
                    quantity=line.product_uom_qty,
                    product=line.product_id,
                    partner=order.partner_id,
                )['total_included']
            else:
                base_total = line.price_total
            remaining = line.cim_selling_price - base_total
            cmp = currency.compare_amounts(remaining, 0)

            if cmp < 0:
                raise UserError(_(
                    "The Selling Price (%(target)s) for \"%(desc)s\" is "
                    "lower than that line's current tax-included amount "
                    "(%(base)s). Increase the Selling Price or review the "
                    "line first.",
                    target=line.cim_selling_price,
                    desc=line.product_id.display_name or line.name,
                    base=base_total,
                ))

            service_line = line.cim_service_line_id
            if service_line and service_line.order_id != order:
                # Stale reference - ignore it.
                service_line = self.env['sale.order.line']

            if cmp == 0:
                # Selling Price already matches this line's own tax-included
                # amount - no Other Income top-up needed.
                if service_line:
                    line.cim_service_line_id = False
                    service_line.unlink()
                continue

            if not vat_tax:
                raise UserError(_(
                    "None of the order lines have a VAT (non-Excise) sale "
                    "tax configured, so there is no tax to apply on the "
                    "Other Income line for \"%(desc)s\". Please set a Sales "
                    "Tax on the product first.",
                    desc=line.product_id.display_name or line.name,
                ))

            vat_rate = vat_tax.amount or 0.0
            price_unit = currency.round(remaining / (1 + vat_rate / 100.0))
            service_taxes = vat_tax | wht_taxes

            line_vals = {
                'product_uom_qty': 1.0,
                'price_unit': price_unit,
                'discount': 0.0,
                'tax_id': [(6, 0, service_taxes.ids)],
                'name': service_product.name,
            }

            if service_line:
                unchanged = (
                    currency.compare_amounts(service_line.price_unit, price_unit) == 0
                    and service_line.product_uom_qty == 1.0
                    and not service_line.discount
                    and service_line.tax_id == service_taxes
                    and service_line.name == service_product.name
                )
                if not unchanged:
                    service_line.write(line_vals)
            else:
                line_vals.update({
                    'order_id': order.id,
                    'product_id': service_product.id,
                    # Keep the Other Income line right after its product line.
                    'sequence': line.sequence,
                })
                line.cim_service_line_id = self.env['sale.order.line'].with_context(
                    cim_skip_auto_balance=True
                ).create(line_vals)

        return True

    # ------------------------------------------------------------------
    # Order -> Invoice / duplicate
    # ------------------------------------------------------------------
    def _prepare_invoice(self):
        """Carry the order's Reference onto the invoice (regular, final and
        down-payment invoices all go through here)."""
        vals = super()._prepare_invoice()
        if self.cim_reference:
            vals['cim_reference'] = self.cim_reference
        return vals

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        moves._cim_link_sale_service_lines()
        return moves

    def copy(self, default=None):
        """Duplicating a balanced quotation keeps it balanced: the Selling
        Price and the Other Income link are re-established on the copy."""
        new_order = super().copy(default)
        if default and 'order_line' in default:
            return new_order
        old_lines = self._get_copiable_order_lines()
        new_lines = new_order.order_line
        if len(old_lines) != len(new_lines):
            return new_order
        mapping = dict(zip(old_lines.ids, new_lines))
        for old, new in zip(old_lines, new_lines):
            if old.cim_selling_price:
                # The Service/Other Income line was copied along with the
                # order but is not linked yet: do not auto-balance (that would
                # add a duplicate) - just restore the Selling Price and link.
                new.with_context(cim_skip_auto_balance=True).cim_selling_price = old.cim_selling_price
            if old.cim_service_line_id and old.cim_service_line_id.id in mapping:
                new.cim_service_line_id = mapping[old.cim_service_line_id.id]
        return new_order
