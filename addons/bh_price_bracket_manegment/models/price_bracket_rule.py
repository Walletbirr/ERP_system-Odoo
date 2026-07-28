from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PriceBracketRule(models.Model):
    """Configurable price bracket table.

    Each row defines: 'if a product's Sales Price falls between min_price
    and max_price, apply discount_percent'. Managed from
    Settings > Sales > Price Brackets by any normal Sales Manager user -
    no code changes required to add/edit/remove tiers.
    """
    _name = 'price.bracket.rule'
    _description = 'Price Bracket Discount Rule'
    _order = 'sequence, min_price'

    name = fields.Char(string='Bracket', compute='_compute_name', store=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
        help="Leave empty to apply this bracket for all companies.",
    )
    min_price = fields.Float(
        string='Min Sales Price', required=True,
        help="Inclusive lower bound of the bracket.",
    )
    max_price = fields.Float(
        string='Max Sales Price',
        help="Inclusive upper bound of the bracket. Ignored (and can be "
             "left at 0) if 'No upper limit' is checked.",
    )
    no_max = fields.Boolean(
        string='No upper limit',
        help="Check this for the top tier of your bracket table - e.g. "
             "'10,001 and above'. When checked, Max Sales Price is "
             "ignored and this bracket matches any price at or above "
             "Min Sales Price, no matter how high. Only one active "
             "bracket per company should have this checked.",
    )
    discount_percent = fields.Float(
        string='Discount %', required=True,
        help="Percentage discount applied to the Sales Price when a "
             "product's list price falls inside this bracket.",
    )

    @api.depends('min_price', 'max_price', 'discount_percent', 'no_max')
    def _compute_name(self):
        for rec in self:
            if rec.no_max:
                rec.name = "%.2f and above  ->  %.2f%% off" % (
                    rec.min_price, rec.discount_percent
                )
            else:
                rec.name = "%.2f - %.2f  ->  %.2f%% off" % (
                    rec.min_price, rec.max_price, rec.discount_percent
                )

    @api.constrains('min_price', 'max_price', 'no_max')
    def _check_range(self):
        for rec in self:
            if rec.min_price < 0:
                raise ValidationError("Min Sales Price cannot be negative.")
            if rec.no_max:
                continue
            if rec.max_price < 0:
                raise ValidationError("Max Sales Price cannot be negative.")
            if rec.min_price >= rec.max_price:
                raise ValidationError(
                    "Min Sales Price must be strictly lower than Max Sales "
                    "Price (bracket: %.2f - %.2f). If this is meant to be "
                    "your open-ended top tier, check 'No upper limit' "
                    "instead of setting a Max Sales Price." % (
                        rec.min_price, rec.max_price
                    )
                )

    @api.constrains('min_price', 'max_price', 'no_max', 'company_id', 'active')
    def _check_overlap(self):
        for rec in self:
            if not rec.active:
                continue
            rec_max = float('inf') if rec.no_max else rec.max_price
            domain = [('id', '!=', rec.id), ('active', '=', True)]
            if rec.company_id:
                domain += ['|', ('company_id', '=', rec.company_id.id), ('company_id', '=', False)]
            others = self.search(domain)
            for other in others:
                other_max = float('inf') if other.no_max else other.max_price
                if rec.min_price <= other_max and other.min_price <= rec_max:
                    raise ValidationError(
                        "This bracket (%s) overlaps with an existing "
                        "bracket: %s. Adjust the ranges so brackets never "
                        "overlap." % (rec.name, other.name)
                    )

    @api.model
    def _get_discount_for_price(self, price, company=None):
        """Return the discount percent (float) matching the given price.

        Returns 0.0 if no bracket matches (safe fallback - no discount
        rather than raising an error mid-quotation).
        """
        company = company or self.env.company
        base_domain = [
            ('min_price', '<=', price),
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
        ]
        domain = base_domain + ['|', ('no_max', '=', True), ('max_price', '>=', price)]
        rule = self.sudo().search(domain, limit=1, order='sequence, min_price')
        return rule.discount_percent if rule else 0.0
