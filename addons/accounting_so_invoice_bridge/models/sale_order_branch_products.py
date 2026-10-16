from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_branch_product_tmpl_ids = fields.Many2many(
        'product.template', compute='_compute_x_branch_product_tmpl_ids',
        string='Products Available in Branch',
        help="Technical: products offered on the order lines (services/"
             "consumables, storable products with free stock in the branch "
             "or in another branch that could transfer it). See "
             "_get_branch_filter_mode. Drives the product filter.")
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
    def _get_branch_filter_mode(self):
        """How strictly the order lines are filtered by branch stock.
        Set the system parameter
        `accounting_so_invoice_bridge.branch_filter_mode` to:
          - 'transferable': services/consumables, products with
            free stock in the Deduction Branch, AND products that have
            free stock in ANY other branch. The last group is what makes
            "Request Stock" usable: the salesperson can pick a product
            the branch has run out of, get the warning and ask Inventory
            for an internal transfer.
          - 'all' (default): no stock filter at all (every sellable
            product, even with zero stock anywhere). The warning on pick
            and the block on Confirm still apply.
          - 'branch_only': the old behaviour (only products with free
            stock in the Deduction Branch)."""
        mode = self.env['ir.config_parameter'].sudo().get_param(
            'accounting_so_invoice_bridge.branch_filter_mode',
            'all')
        return mode if mode in ('transferable', 'all', 'branch_only') \
            else 'all'

    @api.depends('warehouse_id', 'company_id')
    def _compute_x_branch_product_tmpl_ids(self):
        Product = self.env['product.product'].sudo()
        Template = self.env['product.template'].sudo()
        mode = self._get_branch_filter_mode()
        cache = {}
        for order in self:
            warehouse = order._get_stock_branch()
            if not warehouse or mode == 'all':
                # No branch chosen yet (or filter disabled): do not
                # restrict anything.
                key = ('all', order.company_id.id)
                if key not in cache:
                    cache[key] = Template.search([
                        ('sale_ok', '=', True),
                        '|', ('company_id', '=', False),
                        ('company_id', '=', order.company_id.id)])
                order.x_branch_product_tmpl_ids = cache[key]
                continue
            if mode == 'branch_only':
                key = ('branch', warehouse.id)
                if key not in cache:
                    cache[key] = Product.with_context(
                        warehouse_id=warehouse.id).search([
                            ('sale_ok', '=', True),
                            '|', ('is_storable', '=', False),
                            ('free_qty', '>', 0)]).product_tmpl_id
            else:
                # 'transferable': free stock in any warehouse. Without a
                # warehouse/location in the context Odoo counts every
                # internal location of the allowed companies.
                key = ('company', order.company_id.id)
                if key not in cache:
                    cache[key] = Product.with_company(
                        order.company_id).search([
                            ('sale_ok', '=', True),
                            '|', ('is_storable', '=', False),
                            ('free_qty', '>', 0)]).product_tmpl_id
            order.x_branch_product_tmpl_ids = cache[key]

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


PART_NUMBER_FIELDS_PARAM = 'accounting_so_invoice_bridge.part_number_fields'
PART_NUMBER_FIELDS_DEFAULT = (
    'default_code,barcode,part_number,x_part_number,part_no,x_part_no,'
    'x_studio_part_number')


_PN_LABEL_WORDS = ('reference', 'part number', 'part no', 'part code',
                   'part #', 'sku', 'item code', 'product code',
                   'internal code')
_PN_SKIP = {'display_name', 'name', 'description', 'description_sale',
            'description_purchase', 'description_picking',
            'description_pickingout', 'description_pickingin',
            'type', 'detailed_type', 'tracking', 'sale_line_warn_msg',
            'purchase_line_warn_msg', 'invoice_policy'}


def _part_number_search_fields(model):
    """Fields searched besides the name: the names listed in the system
    parameter, plus every Char field whose label looks like a reference /
    part number / code (catches custom fields added by other modules)."""
    names = model.env['ir.config_parameter'].sudo().get_param(
        PART_NUMBER_FIELDS_PARAM, PART_NUMBER_FIELDS_DEFAULT)
    wanted = {n.strip() for n in names.split(',') if n.strip()}
    for fname, field in model._fields.items():
        label = (field.string or '').lower()
        if (field.type == 'char' and fname not in _PN_SKIP
                and any(w in label for w in _PN_LABEL_WORDS)):
            wanted.add(fname)
    return sorted(
        f for f in wanted
        if f in model._fields and model._fields[f].type == 'char'
        and (model._fields[f].store or model._fields[f].search))


def _extra_search_domain(model, operator, value):
    """Domain matching `value` on custom reference / part-number fields
    (default_code and barcode are already handled by Odoo itself)."""
    if not value or operator not in ('ilike', 'like', '=', '=ilike'):
        return []
    fields_ = [f for f in _part_number_search_fields(model)
               if f not in ('default_code', 'barcode')]
    if not fields_:
        return []
    return expression.OR([[(f, operator, value)] for f in fields_])


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        # Odoo 18 (product.template.name_search) switches the search on the
        # variants' Internal Reference / barcode OFF whenever the domain has
        # a condition on 'id'. The order-line filter is exactly that
        # ('id', 'in', branch products), so typing a reference found
        # nothing. Ask for the variant search explicitly.
        if name and 'search_product_product' not in self.env.context:
            self = self.with_context(search_product_product=True)
        return super().name_search(
            name=name, args=args, operator=operator, limit=limit)

    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        extra = _extra_search_domain(self, operator, value)
        return expression.OR([domain, extra]) if extra else domain


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        extra = _extra_search_domain(self, operator, value)
        return expression.OR([domain, extra]) if extra else domain
