# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


def cim_is_wht_tax(tax):
    """Withholding taxes are configured as NEGATIVE percentage taxes
    (Accounting > Configuration > Taxes, tax group "Withholding Tax").
    They must never be mistaken for the invoice's VAT tax."""
    return tax.amount_type == 'percent' and (tax.amount or 0.0) < 0


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Free-text Reference shown in the header of customer invoices / credit
    # notes. copy=True on purpose: a credit note (reversal) and a duplicated
    # draft keep the reference of the invoice they come from.
    cim_reference = fields.Char(
        string="Reference",
        copy=True,
        tracking=True,
        help="Free-text reference of this document. When the invoice is "
             "generated from a sales order, the order's Reference is "
             "carried over here automatically.",
    )

    # Gap 3: a display-only copy of invoice_line_ids used solely by the
    # "Invoice Lines" tab, so the Service Charge lines (and any other
    # product flagged 'Hide From Invoice Lines Tab') don't clutter that
    # grid. It shares the same inverse field ('move_id') as
    # invoice_line_ids, so it is not a copy of the data - it points at the
    # very same account.move.line records. Nothing here changes what those
    # lines are, only which subset of them is displayed in this particular
    # grid. Totals, taxes and the "Journal Items" tab (which reads the
    # unrestricted line_ids field) are completely unaffected, and the
    # lines still print normally on the PDF.
    cim_invoice_line_ids_display = fields.One2many(
        'account.move.line', 'move_id',
        string="Invoice Lines",
        copy=False,
        domain=[
            ('display_type', 'in', ('product', 'line_section', 'line_note')),
            ('cim_hide_from_invoice_lines', '=', False),
        ],
    )

    # Custom totals box shown at the bottom of the "Invoice Lines" tab,
    # replacing the native Untaxed Amount / tax breakdown / Total widget
    # for customer invoices and credit notes. These are purely for
    # DISPLAY: the real accounting (journal items, taxes, amount_total,
    # the printed invoice/report) still comes from the normal Odoo fields
    # and is completely untouched.
    cim_product_untaxed_amount = fields.Monetary(
        string="Untaxed Amount",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Untaxed Amount of the product line(s) only - excludes the "
             "auto-generated Service Charge line(s).",
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
        string="Service Charge",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Untaxed total of the auto-generated Service Charge line(s) "
             "on this invoice.",
    )
    cim_before_vat_amount = fields.Monetary(
        string="Before Vat",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Subtotal plus Service Charge - i.e. the full taxable base "
             "that VAT is then computed on.",
    )
    cim_vat_amount = fields.Monetary(
        string="Vat",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Total VAT (tax other than Excise Tax), across all lines "
             "including the Service Charge line(s).",
    )

    cim_wht_amount = fields.Monetary(
        string="Withholding Tax",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Total withholding tax on this invoice (shown as a negative "
             "amount: it is deducted from what the customer pays).",
    )
    cim_total_before_wht = fields.Monetary(
        string="Total Before WHT",
        currency_field='currency_id',
        compute='_compute_cim_totals',
        help="Total including VAT / Excise but before the withholding "
             "tax deduction.",
    )

    @api.depends(
        'amount_untaxed',
        'amount_tax',
        'currency_id',
        'amount_total',
        'line_ids.balance',
        'line_ids.amount_currency',
        'line_ids.tax_line_id',
        'invoice_line_ids.price_subtotal',
        'invoice_line_ids.product_id',
    )
    def _compute_cim_totals(self):
        service_product = self.env.ref(
            'custom_invoice_management.product_service_charge', raise_if_not_found=False
        )
        for move in self:
            excise_lines = move.line_ids.filtered(
                lambda l: l.tax_line_id and l.tax_line_id.include_base_amount
            )
            excise_amount = abs(sum(excise_lines.mapped('balance')))

            if service_product:
                service_lines = move.invoice_line_ids.filtered(
                    lambda l: l.product_id == service_product
                )
                service_charge_amount = sum(service_lines.mapped('price_subtotal'))
            else:
                service_charge_amount = 0.0

            # Withholding tax: negative-percentage tax lines. In document
            # terms (invoice: tax line is a credit, refund: a debit) the
            # sign is flipped so the result reads as a negative deduction.
            wht_lines = move.line_ids.filtered(
                lambda l: l.tax_line_id and cim_is_wht_tax(l.tax_line_id)
            )
            sign = -1 if move.move_type == 'out_invoice' else 1
            wht_amount = sign * sum(wht_lines.mapped('amount_currency'))

            move.cim_service_charge_amount = service_charge_amount
            move.cim_excise_tax_amount = excise_amount
            move.cim_wht_amount = wht_amount
            move.cim_total_before_wht = move.amount_total - wht_amount
            move.cim_vat_amount = move.amount_tax - excise_amount - wht_amount
            move.cim_product_untaxed_amount = move.amount_untaxed - service_charge_amount
            move.cim_subtotal_before_vat = move.cim_product_untaxed_amount + excise_amount
            move.cim_before_vat_amount = move.cim_subtotal_before_vat + service_charge_amount

    # Fields of the invoice whose change can alter what a line is worth, so
    # the Service Charge lines have to be re-balanced when they are written.
    _CIM_REBALANCE_MOVE_FIELDS = frozenset({
        'invoice_line_ids', 'partner_id', 'fiscal_position_id', 'currency_id',
    })

    @api.model
    def _cim_get_service_charge_product(self):
        product = self.env.ref(
            'custom_invoice_management.product_service_charge', raise_if_not_found=False
        )
        if not product:
            raise UserError(_(
                "The 'Service Charge' product could not be found. "
                "Please reinstall this module or create a product with "
                "external ID 'custom_invoice_management.product_service_charge'."
            ))
        return product

    def _cim_get_common_vat_tax(self, candidate_lines, service_product):
        """The single VAT tax to charge on every Service Charge line on
        this invoice: the first non-Excise sale tax found on any of the
        invoice's own product lines (Excise Tax is identified generically
        as any tax with "Affect Base of Subsequent Taxes" enabled). All
        products are expected to share the same VAT tax, so it only needs
        to be found once per invoice rather than picked per line.
        """
        self.ensure_one()
        for line in candidate_lines:
            vat_taxes = line.tax_ids.filtered(
                lambda t: t.type_tax_use == 'sale'
                and not t.include_base_amount
                and not cim_is_wht_tax(t)
            )
            if vat_taxes:
                return vat_taxes[0]
        return self.env['account.tax']

    # ------------------------------------------------------------------
    # Automatic balance
    # ------------------------------------------------------------------
    @staticmethod
    def _cim_vals_have_selling_price(vals_list):
        """True when create() values carry an explicit Selling Price on an
        invoice line (e.g. an invoice generated with a target price)."""
        for vals in vals_list:
            for cmd in vals.get('invoice_line_ids') or []:
                if (isinstance(cmd, (list, tuple)) and len(cmd) == 3
                        and isinstance(cmd[2], dict)
                        and cmd[2].get('cim_selling_price')):
                    return True
        return False

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('cim_skip_auto_balance'):
            return super().create(vals_list)
        has_price = self._cim_vals_have_selling_price(vals_list)
        moves = super(AccountMove, self.with_context(cim_skip_auto_balance=True)).create(vals_list)
        if has_price:
            moves._cim_auto_balance()
        return moves

    def write(self, vals):
        if (self.env.context.get('cim_skip_auto_balance')
                or not self._CIM_REBALANCE_MOVE_FIELDS.intersection(vals)):
            return super().write(vals)
        # Let the whole write finish first (lines included), then balance once.
        res = super(AccountMove, self.with_context(cim_skip_auto_balance=True)).write(vals)
        self._cim_auto_balance()
        return res

    def _cim_check_selling_price_before_post(self):
        """Every product line needs a Selling Price before the invoice can
        be posted (it is what drives the Service Charge line / the total)."""
        service_product = self.env.ref(
            'custom_invoice_management.product_service_charge', raise_if_not_found=False
        )
        for move in self.filtered(
                lambda m: m.state == 'draft' and m.move_type in ('out_invoice', 'out_refund')):
            missing = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
                and l.product_id
                and l.product_id != service_product
                and not l.cim_hide_from_invoice_lines
                and not ('is_downpayment' in l._fields and l.is_downpayment)
                and not l.cim_selling_price
                # A line worth nothing has nothing to balance.
                and not move.currency_id.is_zero(l.price_total)
            )
            if missing:
                raise UserError(_(
                    "A Selling Price is required on every invoice line "
                    "before the invoice can be posted.\n\n"
                    "Missing on:\n%(lines)s\n\n"
                    "Enter it in the Selling Price column and save.",
                    lines="\n".join(
                        "- %s" % (l.product_id.display_name or l.name) for l in missing
                    ),
                ))

    def action_post(self):
        self._cim_check_selling_price_before_post()
        return super().action_post()

    def copy(self, default=None):
        """Duplicating a balanced invoice keeps it balanced: the Selling
        Price and the Service Charge link are re-established on the copy."""
        new_moves = super().copy(default)
        if default and 'invoice_line_ids' in default:
            return new_moves
        for old, new in zip(self, new_moves):
            old_lines = old.invoice_line_ids
            new_lines = new.invoice_line_ids
            if len(old_lines) != len(new_lines):
                continue
            mapping = dict(zip(old_lines.ids, new_lines))
            for o, n in zip(old_lines, new_lines):
                if o.cim_selling_price and o.cim_service_line_id:
                    # The Service Charge line was copied along but is not
                    # linked yet: restore Selling Price and link without
                    # auto-balancing (that would add a duplicate).
                    n.with_context(cim_skip_auto_balance=True).write({
                        'cim_selling_price': o.cim_selling_price,
                    })
                if o.cim_service_line_id and o.cim_service_line_id.id in mapping:
                    n.with_context(cim_skip_auto_balance=True).write({
                        'cim_service_line_id': mapping[o.cim_service_line_id.id].id,
                    })
        return new_moves

    def action_cim_balance(self):
        """Balance this invoice on demand.

        The invoice is balanced automatically every time it is saved (see
        ``_cim_auto_balance``), so the form has no Balance button any more.
        This method stays available for server actions / scripts and, unlike
        the automatic run, complains when no line has a Selling Price.
        """
        self.ensure_one()

        if self.move_type not in ('out_invoice', 'out_refund'):
            raise UserError(_(
                "Balancing is only available on customer invoices and "
                "credit notes."
            ))
        if self.state != 'draft':
            raise UserError(_(
                "This invoice is no longer a draft; reset it to draft "
                "before balancing."
            ))
        self._cim_balance(strict=True)
        return True

    def _cim_auto_balance(self):
        """Silent balance run on save. Only draft customer invoices / credit
        notes are touched; an invoice without any Selling Price is left alone."""
        for move in self:
            if move.state == 'draft' and move.move_type in ('out_invoice', 'out_refund'):
                move._cim_balance(strict=False)

    def _cim_balance(self, strict=False):
        """For every invoice line where a "Selling Price" (tax incl.) is set,
        add/update a Service Charge line - taxed at the invoice's common VAT
        tax - so that the line's own price_total plus its Service Charge line
        equals the negotiated Selling Price.

        Each product line keeps its own dedicated Service Charge line
        (tracked via cim_service_line_id) so several lines with different
        targets can be balanced independently on the same invoice.

        :param strict: raise when no line has a Selling Price instead of
            quietly doing nothing.
        """
        self.ensure_one()
        # Everything written below must not trigger another balance run.
        move = self.with_context(cim_skip_auto_balance=True)
        service_product = move._cim_get_service_charge_product()

        # Real product lines only - the Service Charge lines this action
        # itself generates are excluded so they never get balanced again.
        candidate_lines = move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
            and l.product_id != service_product
            and not ('is_downpayment' in l._fields and l.is_downpayment)
        )

        # Lines whose target was cleared: drop their old Service Charge line.
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
                    "Please enter a Selling Price on at least one invoice "
                    "line before balancing."
                ))
            return False

        vat_tax = move._cim_get_common_vat_tax(candidate_lines, service_product)
        currency = move.currency_id
        income_account = None

        for line in lines_to_balance:
            # The Selling Price is the VAT/Excise-inclusive price agreed with
            # the customer. Withholding tax is a deduction on top of it, so it
            # must not count towards the line's own total here.
            wht_taxes = line.tax_ids.filtered(cim_is_wht_tax)
            if wht_taxes:
                net_taxes = line.tax_ids - wht_taxes
                base_total = net_taxes.compute_all(
                    line.price_unit * (1 - (line.discount or 0.0) / 100.0),
                    currency=line.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=move.partner_id,
                    is_refund=move.move_type == 'out_refund',
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
            if service_line and service_line.move_id != move:
                # Stale reference (e.g. after a duplicate) - ignore it.
                service_line = self.env['account.move.line']

            if cmp == 0:
                # Selling Price already matches this line's own tax-included
                # amount - no Service Charge top-up needed.
                if service_line:
                    line.cim_service_line_id = False
                    service_line.unlink()
                continue

            if not vat_tax:
                raise UserError(_(
                    "None of the invoice lines have a VAT (non-Excise) "
                    "sale tax configured, so there is no tax to apply on "
                    "the Service Charge for \"%(desc)s\". Please set a "
                    "Sales Tax on the product first.",
                    desc=line.product_id.display_name or line.name,
                ))

            vat_rate = vat_tax.amount or 0.0
            price_unit = currency.round(remaining / (1 + vat_rate / 100.0))
            service_taxes = vat_tax | wht_taxes

            line_vals = {
                'quantity': 1.0,
                'price_unit': price_unit,
                'tax_ids': [(6, 0, service_taxes.ids)],
                'name': service_product.name,
            }

            if service_line:
                unchanged = (
                    currency.compare_amounts(service_line.price_unit, price_unit) == 0
                    and service_line.quantity == 1.0
                    and service_line.tax_ids == service_taxes
                    and service_line.name == service_product.name
                )
                if not unchanged:
                    service_line.write(line_vals)
            else:
                if income_account is None:
                    income_account = (
                        move.company_id.cim_service_charge_account_id
                        or service_product.property_account_income_id
                        or service_product.categ_id.property_account_income_categ_id
                    )
                    if not income_account:
                        raise UserError(_(
                            "No Income Account is configured for the "
                            "Service Charge line. Set one in Accounting > "
                            "Configuration > Settings > Custom Invoice "
                            "Management (\"Service Charge Income "
                            "Account\"), or directly on the Service Charge "
                            "product / its Product Category."
                        ))
                line_vals.update({
                    'move_id': move.id,
                    'product_id': service_product.id,
                    'account_id': income_account.id,
                })
                new_line = self.env['account.move.line'].with_context(
                    cim_skip_auto_balance=True
                ).create(line_vals)
                line.cim_service_line_id = new_line.id

        return True
