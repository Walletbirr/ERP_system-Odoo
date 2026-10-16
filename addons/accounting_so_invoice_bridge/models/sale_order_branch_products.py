from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_branch_product_tmpl_ids = fields.Many2many(
        'product.template', compute='_compute_x_branch_product_tmpl_ids',
        string='Products Available in Branch',
        help="Technical: products the order's branch can sell right now "
             "(services/consumables, plus storable products with free "
             "stock in the branch). Drives the product filter on the "
             "order lines.")
    x_stock_request_ids = fields.One2many(
        'sale.stock.request', 'sale_order_id', string='Stock Requests')
    x_stock_request_count = fields.Integer(
        compute='_compute_x_stock_request_count')

    def _get_stock_branch(self):
        """The branch whose stock filters the product lines and receives
        the internal transfer. This is the Deduction Branch, because that
        is where the stock is taken from. To filter on the reporting
        Branch instead, return self.x_sale_branch_id here."""
        self.ensure_one()
        return self.warehouse_id

    @api.depends('warehouse_id', 'company_id')
    def _compute_x_branch_product_tmpl_ids(self):
        Product = self.env['product.product'].sudo()
        cache = {}
        for order in self:
            warehouse = order._get_stock_branch()
            if not warehouse:
                # No branch chosen yet: do not restrict anything.
                order.x_branch_product_tmpl_ids = self.env[
                    'product.template'].sudo().search([('sale_ok', '=', True)])
                continue
            if warehouse.id not in cache:
                products = Product.with_context(
                    warehouse_id=warehouse.id).search([
                        ('sale_ok', '=', True),
                        '|', ('is_storable', '=', False),
                        ('free_qty', '>', 0)])
                cache[warehouse.id] = products.product_tmpl_id
            order.x_branch_product_tmpl_ids = cache[warehouse.id]

    @api.depends('x_stock_request_ids')
    def _compute_x_stock_request_count(self):
        for order in self:
            order.x_stock_request_count = len(order.x_stock_request_ids)

    def _prepare_stock_request_lines(self):
        """Lines to pre-fill in the request form.
        - Products the branch can not supply: the missing quantity.
        - Otherwise (nothing missing): the storable products of the order,
          so a one-product order opens with that product already there.
        - Empty order: nothing, the salesperson picks the products."""
        self.ensure_one()
        commands = []
        for issue in self._branch_stock_issues():
            missing = issue['needed'] - issue['available']
            if missing > 0:
                commands.append((0, 0, {
                    'product_id': issue['product'].id,
                    'quantity': missing}))
        if commands:
            return commands
        demand = {}
        for line in self.order_line:
            product = line.product_id
            if (line.display_type or not product or not product.is_storable
                    or line.product_uom_qty <= 0 or not line.product_uom):
                continue
            demand[product] = demand.get(product, 0.0) + \
                line.product_uom._compute_quantity(
                    line.product_uom_qty, product.uom_id)
        return [(0, 0, {'product_id': p.id, 'quantity': q})
                for p, q in demand.items()]

    def action_request_stock(self):
        """Open the request form (a dialog) for this order."""
        self.ensure_one()
        if self.state not in ('draft', 'sent', 'sale'):
            raise UserError(_("You cannot request stock for a cancelled "
                              "order."))
        if not self.warehouse_id:
            raise UserError(_("Select the Deduction Branch first."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Request Stock from Inventory"),
            'res_model': 'sale.stock.request',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_warehouse_id': self.warehouse_id.id,
                'default_line_ids': self._prepare_stock_request_lines(),
                'dialog_size': 'large',
            },
        }

    def action_view_stock_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Stock Requests"),
            'res_model': 'sale.stock.request',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id,
                        'default_warehouse_id': self.warehouse_id.id},
        }
