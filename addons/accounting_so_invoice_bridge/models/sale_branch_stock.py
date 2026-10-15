from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

PARAM_BLOCK = 'accounting_so_invoice_bridge.block_unavailable_stock'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Two different warehouse questions on one quotation:
    #   warehouse_id (Odoo's own field, labelled "Deduction Branch"):
    #       the stock is taken from here and the delivery starts here.
    #   x_sale_branch_id ("Branch"): the branch where the SALE happened,
    #       used for reporting. It does not move any stock.
    @api.model
    def _default_sale_branch_id(self):
        user = self.env.user
        warehouse = False
        if hasattr(user, '_get_default_warehouse_id'):
            warehouse = user._get_default_warehouse_id()
        if not warehouse:
            warehouse = self.env['stock.warehouse'].search(
                [('company_id', '=', self.env.company.id)], limit=1)
        return warehouse.id or False

    x_sale_branch_id = fields.Many2one(
        'stock.warehouse', string='Branch',
        default=lambda self: self._default_sale_branch_id(),
        domain="[('company_id', '=', company_id)]",
        tracking=True, copy=False, index=True,
        help="The branch where this sale happened (for reporting). "
             "Stock is taken from the Deduction Branch.")

    # ------------------------------------------------------------------
    # Deduction Branch (= Warehouse) stock check
    # ------------------------------------------------------------------
    def _branch_free_qty(self, product, warehouse):
        """Quantity of `product` that is free (on hand minus reserved) in
        `warehouse`, in the product's own unit of measure. Read with sudo:
        a salesperson may check stock without owning stock rights."""
        return product.sudo().with_context(
            warehouse_id=warehouse.id).free_qty

    def _branch_stock_issues(self):
        """Storable products of this order that the chosen branch can not
        deliver. Returns a list of dicts (empty = everything available).
        The demand of a product is the SUM of all its lines, so two lines
        of the same product can't each pass on their own.
        Not checked: services, consumables without tracking, and products
        that are replenished on order (MTO)."""
        self.ensure_one()
        warehouse = self.warehouse_id
        if not warehouse:
            return []
        demand = {}
        for line in self.order_line:
            product = line.product_id
            if (line.display_type or not product or not product.is_storable
                    or getattr(line, 'is_mto', False)
                    or line.product_uom_qty <= 0 or not line.product_uom):
                continue
            demand[product] = demand.get(product, 0.0) + \
                line.product_uom._compute_quantity(
                    line.product_uom_qty, product.uom_id)
        if not demand:
            return []
        others = self.env['stock.warehouse'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('id', '!=', warehouse.id)])
        issues = []
        for product, needed in demand.items():
            free = self._branch_free_qty(product, warehouse)
            if float_compare(free, needed,
                             precision_rounding=product.uom_id.rounding) >= 0:
                continue
            alternatives = []
            for other in others:
                other_free = self._branch_free_qty(product, other)
                if float_compare(
                        other_free, needed,
                        precision_rounding=product.uom_id.rounding) >= 0:
                    alternatives.append((other.name, other_free))
            issues.append({
                'product': product, 'needed': needed,
                'available': max(free, 0.0), 'alternatives': alternatives,
            })
        return issues

    def _branch_stock_message(self, issues):
        self.ensure_one()
        parts = []
        for issue in issues:
            product = issue['product']
            text = _(
                "- %(product)s: %(available).2f available in this branch, "
                "%(needed).2f needed (%(uom)s).",
                product=product.display_name, available=issue['available'],
                needed=issue['needed'], uom=product.uom_id.name)
            if issue['alternatives']:
                text += " " + _("In stock at: %s.", ", ".join(
                    "%s (%.2f)" % alt for alt in issue['alternatives']))
            else:
                text += " " + _("No other branch has enough stock.")
            parts.append(text)
        return _(
            "Deduction Branch \"%(branch)s\" cannot supply this order:"
            "\n\n%(lines)s\n\n"
            "Please choose another Deduction Branch, or reduce the "
            "quantity.",
            branch=self.warehouse_id.name, lines="\n".join(parts))

    def _branch_stock_blocking_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            PARAM_BLOCK, '1') not in ('0', 'False', 'false')

    @api.onchange('warehouse_id')
    def _onchange_warehouse_branch_stock(self):
        """Branch changed: re-check every line right away."""
        for order in self:
            if not order.order_line:
                continue
            issues = order._branch_stock_issues()
            if issues:
                return {'warning': {
                    'title': _("Product not available in the Deduction Branch"),
                    'message': order._branch_stock_message(issues)}}

    def action_confirm(self):
        # Hard stop (the onchange above is only a heads-up): a quotation
        # cannot become an order for a branch that has no stock.
        if self._branch_stock_blocking_enabled():
            for order in self.filtered(lambda o: o.state in ('draft', 'sent')):
                issues = order._branch_stock_issues()
                if issues:
                    raise UserError(order._branch_stock_message(issues))
        return super().action_confirm()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_id', 'product_uom_qty', 'product_uom')
    def _onchange_branch_stock_check(self):
        """Heads-up while the salesperson picks the product / quantity."""
        for line in self:
            order = line.order_id
            if not line.product_id or not order.warehouse_id:
                continue
            issues = [i for i in order._branch_stock_issues()
                      if i['product'] == line.product_id]
            if issues:
                return {'warning': {
                    'title': _("Product not available in the Deduction Branch"),
                    'message': order._branch_stock_message(issues)}}
