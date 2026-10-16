from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_branch_product_tmpl_ids = fields.Many2many(
        'product.template', compute='_compute_x_branch_product_tmpl_ids',
        string='Products of the Branch',
        help="Technical: products the order's branch carries (see "
             "_get_branch_product_filter_mode). Drives the product filter "
             "on the order lines. Stock shortages are NOT filtered out: "
             "they are caught by the stock warning, which offers Request "
             "Stock.")
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

    @api.model
    def _get_branch_product_filter_mode(self):
        """System parameter accounting_so_invoice_bridge.branch_product_filter
        branch    (default) the products this branch carries: stock-tracked
                  products that have, had or will get stock in the branch,
                  plus every product without stock tracking.
        available only products with free stock in the branch right now.
        all       no stock filter (every sellable product)."""
        mode = self.env['ir.config_parameter'].sudo().get_param(
            'accounting_so_invoice_bridge.branch_product_filter', 'branch')
        return mode if mode in ('branch', 'available', 'all') else 'branch'

    def _branch_product_ids(self, warehouse, mode):
        """Ids of the product.product the order lines may offer."""
        Product = self.env['product.product'].sudo()
        domain = [('sale_ok', '=', True)]
        if mode == 'all':
            return Product.search(domain).ids
        scoped = Product.with_context(warehouse_id=warehouse.id)
        if mode == 'available':
            return scoped.search(domain + [
                '|', ('is_storable', '=', False),
                ('free_qty', '>', 0)]).ids
        # mode == 'branch': a product belongs to the branch when ...
        view_location = warehouse.view_location_id
        history = set()
        if view_location:
            # ... it has (or had) a stock record there, even at zero ...
            quants = self.env['stock.quant'].sudo()._read_group(
                [('location_id', 'child_of', view_location.id)],
                ['product_id'])
            # ... or any real stock movement came from / went to the branch
            # (sold out, transferred in, delivered, waiting to arrive).
            moves = self.env['stock.move'].sudo()._read_group(
                [('state', 'not in', ('draft', 'cancel')),
                 '|', ('location_id', 'child_of', view_location.id),
                 ('location_dest_id', 'child_of', view_location.id)],
                ['product_id'])
            history = {row[0].id for row in quants + moves if row[0]}
        return scoped.search(domain + [
            '|', '|', '|',
            ('is_storable', '=', False),      # services / untracked goods
            ('qty_available', '!=', 0),       # on hand, even if all reserved
            ('incoming_qty', '>', 0),         # stock arriving soon
            ('id', 'in', list(history)),      # sold out / used to be here
        ]).ids

    @api.depends('warehouse_id', 'company_id')
    def _compute_x_branch_product_tmpl_ids(self):
        Product = self.env['product.product'].sudo()
        mode = self._get_branch_product_filter_mode()
        cache = {}
        for order in self:
            warehouse = order._get_stock_branch()
            if not warehouse:
                # No branch chosen yet: do not restrict anything.
                order.x_branch_product_tmpl_ids = self.env[
                    'product.template'].sudo().search([('sale_ok', '=', True)])
                continue
            if warehouse.id not in cache:
                cache[warehouse.id] = Product.browse(
                    order._branch_product_ids(warehouse, mode)).product_tmpl_id
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


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        # Odoo 18 (product.template.name_search) switches the search on the
        # variants' Internal Reference / barcode OFF whenever the domain has a
        # condition on 'id'. The order-line product filter is exactly that
        # ('id', 'in', branch products), so typing a reference such as
        # "2521P0024" found nothing (only the name was searched).
        # Ask for the variant search explicitly; the branch filter in `args`
        # still applies.
        if name and 'search_product_product' not in self.env.context:
            self = self.with_context(search_product_product=True)
        return super(ProductTemplate, self).name_search(
            name=name, args=args, operator=operator, limit=limit)
