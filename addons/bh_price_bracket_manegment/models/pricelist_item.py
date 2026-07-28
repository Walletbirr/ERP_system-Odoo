from odoo import api, fields, models


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    compute_price = fields.Selection(
        selection_add=[('bracket', 'Price Bracket')],
        ondelete={'bracket': 'set default'},
    )

    def _compute_price(self, *args, **kwargs):
        """Override to handle the 'bracket' compute mode.

        NOTE: The exact positional signature of _compute_price on
        product.pricelist.item has changed slightly across Odoo
        versions (product, quantity, uom, date, currency in 17.0;
        similar in 18.0). We accept *args/**kwargs and pull out
        'product' defensively so this keeps working even if the core
        signature is adjusted in a minor point release. Verify against
        your installed odoo/addons/product/models/product_pricelist_item.py
        if you upgrade Odoo later.
        """
        # `self` can legitimately be an EMPTY recordset here - that's how
        # core Odoo represents "no explicit pricelist item matched this
        # line, just use the base price". Only enforce the singleton
        # check when there's actually a record to check; an unconditional
        # ensure_one() would (and did) crash on every line that falls
        # back to the base price instead of a bracket rule.
        self and self.ensure_one()
        if self.compute_price != 'bracket':
            return super()._compute_price(*args, **kwargs)

        product = kwargs.get('product') or (args[0] if args else None)
        if not product:
            return super()._compute_price(*args, **kwargs)

        base_price = product.list_price
        discount = self.env['price.bracket.rule']._get_discount_for_price(
            base_price, company=self.company_id or self.env.company
        )
        return base_price * (1 - (discount / 100.0))

    # -- Tax-Included Price Helper -----------------------------------
    # Lets a user type in the final, tax-included amount a customer
    # negotiated and have the tax-excluded Fixed Price calculated for
    # them automatically. `target_tax_id` is deliberately kept as a
    # real field (auto-filled, still used server-side) even though the
    # form no longer shows it - see pricelist_item_views.xml.

    target_price_tax_included = fields.Boolean(
        string='Enter Tax-Included Price',
        help="Check this if the price you're negotiating is the final "
             "amount the customer pays, INCLUDING tax. Enter that number "
             "in 'Target Price (Tax Incl.)' and Fixed Price will be "
             "calculated for you automatically using the applicable Tax. "
             "Leave unchecked to keep entering Fixed Price manually, as "
             "before.",
    )
    target_total_price = fields.Monetary(
        string='Selling Price',
        currency_field='currency_id',
        help="The final, tax-included amount the customer should pay.",
    )
    target_tax_id = fields.Many2one(
        'account.tax',
        string='Tax',
        domain="[('type_tax_use', '=', 'sale'), ('amount_type', '=', 'percent'), "
               "'|', ('company_id', '=', company_id), ('company_id', '=', False)]",
        help="Tax used to back-calculate the tax-excluded Fixed Price from "
             "the Target Price above. Auto-filled from the product's own "
             "sales tax when a specific product is selected on this rule, "
             "or from the company's Default Sales Tax when the rule "
             "applies to ALL products.",
    )

    @api.onchange('target_price_tax_included', 'product_id', 'product_tmpl_id')
    def _onchange_autofill_target_tax(self):
        for rec in self:
            if rec.target_tax_id or not rec.target_price_tax_included:
                continue

            company = rec.company_id or self.env.company
            product = rec.product_id or rec.product_tmpl_id
            tax = self.env['account.tax']

            if product:
                tax = product.taxes_id.filtered(
                    lambda t: t.amount_type == 'percent'
                )[:1]

            if not tax:
                tax = company.account_sale_tax_id
                if tax and tax.amount_type != 'percent':
                    tax = self.env['account.tax']

            if not tax:
                candidates = self.env['account.tax'].search([
                    ('type_tax_use', '=', 'sale'),
                    ('amount_type', '=', 'percent'),
                    '|', ('company_id', '=', company.id),
                    ('company_id', '=', False),
                ])
                if len(candidates) == 1:
                    tax = candidates

            if tax:
                rec.target_tax_id = tax

    @api.onchange('target_total_price', 'target_price_tax_included',
                  'target_tax_id', 'compute_price')
    def _onchange_target_total_price(self):
        for rec in self:
            if not rec.target_price_tax_included:
                continue
            if rec.compute_price != 'fixed':
                continue
            if not rec.target_total_price:
                continue
            rec.fixed_price = rec._reverse_tax_included_price(
                rec.target_total_price, rec.target_tax_id
            )

    def _reverse_tax_included_price(self, tax_included_amount, tax):
        self.ensure_one()
        if not tax or tax.amount_type != 'percent' or not tax.amount:
            return tax_included_amount

        rate = tax.amount / 100.0
        untaxed = tax_included_amount / (1 + rate)

        currency = self.currency_id or self.env.company.currency_id
        if currency:
            untaxed = currency.round(untaxed)
        return untaxed

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._apply_target_price_server_side()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {'compute_price', 'target_tax_id', 'target_price_tax_included',
            'target_total_price'} & set(vals.keys()):
            self._apply_target_price_server_side()
        return res

    def _apply_target_price_server_side(self):
        for rec in self:
            if not rec.target_price_tax_included:
                continue
            if rec.compute_price != 'fixed':
                continue
            if not rec.target_total_price:
                continue
            if not rec.target_tax_id:
                continue
            new_fixed_price = rec._reverse_tax_included_price(
                rec.target_total_price, rec.target_tax_id
            )
            if rec.fixed_price != new_fixed_price:
                super(ProductPricelistItem, rec).write(
                    {'fixed_price': new_fixed_price}
                )
