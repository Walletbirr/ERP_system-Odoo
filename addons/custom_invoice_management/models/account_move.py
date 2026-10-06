# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

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

    @api.depends(
        'amount_untaxed',
        'amount_tax',
        'currency_id',
        'line_ids.balance',
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

            move.cim_service_charge_amount = service_charge_amount
            move.cim_excise_tax_amount = excise_amount
            move.cim_vat_amount = move.amount_tax - excise_amount
            move.cim_product_untaxed_amount = move.amount_untaxed - service_charge_amount
            move.cim_subtotal_before_vat = move.cim_product_untaxed_amount + excise_amount
            move.cim_before_vat_amount = move.cim_subtotal_before_vat + service_charge_amount

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
                lambda t: t.type_tax_use == 'sale' and not t.include_base_amount
            )
            if vat_taxes:
                return vat_taxes[0]
        return self.env['account.tax']

    def action_cim_balance(self):
        """For every invoice line where a "Selling Price" (tax incl.) has
        been entered, add/update a Service Charge line - taxed at the
        invoice's common VAT tax - so that the line's own price_total plus
        its Service Charge line equals the negotiated Selling Price.

        Each product line keeps its own dedicated Service Charge line
        (tracked via cim_service_line_id) so several lines with different
        targets can be balanced independently on the same invoice, all
        sharing the one VAT tax found on the invoice's own product lines.
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

        service_product = self._cim_get_service_charge_product()

        # Real product lines only - the Service Charge lines this action
        # itself generates are excluded so they never get balanced again.
        candidate_lines = self.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product' and l.product_id != service_product
        )

        # Lines whose target was cleared: drop their old Service Charge line.
        cleared_lines = candidate_lines.filtered(
            lambda l: not l.cim_selling_price and l.cim_service_line_id
        )
        for line in cleared_lines:
            line.cim_service_line_id.unlink()
            line.cim_service_line_id = False

        lines_to_balance = candidate_lines.filtered(lambda l: l.cim_selling_price)
        if not lines_to_balance:
            raise UserError(_(
                "Please enter a Selling Price on at least one invoice "
                "line before clicking \"Balance\"."
            ))

        vat_tax = self._cim_get_common_vat_tax(candidate_lines, service_product)
        income_account = None

        for line in lines_to_balance:
            base_total = line.price_total
            remaining = line.cim_selling_price - base_total
            cmp = self.currency_id.compare_amounts(remaining, 0)

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
            if service_line and service_line.move_id != self:
                # Stale reference (e.g. after a duplicate) - ignore it.
                service_line = self.env['account.move.line']

            if cmp == 0:
                # Selling Price already matches this line's own
                # tax-included amount - no Service Charge top-up needed.
                if service_line:
                    service_line.unlink()
                    line.cim_service_line_id = False
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
            price_unit = remaining / (1 + vat_rate / 100.0)
            price_unit = self.currency_id.round(price_unit)

            line_vals = {
                'quantity': 1.0,
                'price_unit': price_unit,
                'tax_ids': [(6, 0, [vat_tax.id])],
                'name': service_product.name,
            }

            if service_line:
                service_line.write(line_vals)
            else:
                if income_account is None:
                    income_account = (
                        self.company_id.cim_service_charge_account_id
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
                    'move_id': self.id,
                    'product_id': service_product.id,
                    'account_id': income_account.id,
                })
                new_line = self.env['account.move.line'].create(line_vals)
                line.cim_service_line_id = new_line.id

        return True
