import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

MANAGER_GROUP = 'stock.group_stock_manager'
DEFAULT_ACCEPT_TEXT = "We will proceed to Internal Transfer"
DEFAULT_REJECT_TEXT = "Not available, we cannot supply this product"
# Only the Inventory Manager may touch these (see write()).
RESPONSE_FIELDS = {'state', 'response', 'responded_by', 'responded_date',
                   'picking_id'}


class SaleStockRequest(models.Model):
    _name = 'sale.stock.request'
    _description = 'Branch Stock Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', default='New', copy=False,
                       readonly=True, index=True)
    sale_order_id = fields.Many2one(
        'sale.order', string='Sales Order', required=True, index=True,
        ondelete='cascade', copy=False)
    # Stored copies: an Inventory Manager has no Sales access, so they
    # must never need to read the sale.order record to see these.
    sale_order_name = fields.Char(
        related='sale_order_id.name', string='Order', store=True)
    salesperson_id = fields.Many2one(
        'res.users', string='Salesperson', default=lambda s: s.env.user,
        required=True, tracking=True, index=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Requesting Branch', required=True,
        tracking=True, index=True,
        help="The branch that needs the stock (the order's Deduction "
             "Branch). The internal transfer goes TO this branch.")
    company_id = fields.Many2one(
        'res.company', related='sale_order_id.company_id', store=True,
        index=True)
    line_ids = fields.One2many(
        'sale.stock.request.line', 'request_id', string='Products',
        copy=True)
    line_summary = fields.Char(string='Products',
                               compute='_compute_line_summary')
    note = fields.Text(string='Note for Inventory',
                       help="Anything the Inventory Manager should know "
                            "(customer deadline, urgency...).")
    state = fields.Selection([
        ('requested', 'Requested'),
        ('accepted', 'Internal Transfer Planned'),
        ('rejected', 'Not Available'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='requested', required=True, tracking=True, copy=False,
        index=True)
    response = fields.Text(string='Inventory Response', tracking=True,
                           copy=False)
    responded_by = fields.Many2one('res.users', string='Answered By',
                                   readonly=True, copy=False)
    responded_date = fields.Datetime(string='Answered On', readonly=True,
                                     copy=False)
    picking_id = fields.Many2one(
        'stock.picking', string='Internal Transfer', copy=False,
        ondelete='set null', tracking=True,
        domain="[('picking_type_code', '=', 'internal')]",
        help="Created by 'Start Internal Transfer'. When it is validated "
             "this request becomes Done automatically.")
    can_respond = fields.Boolean(compute='_compute_can_respond')

    # ------------------------------------------------------------------
    # Computes / helpers
    # ------------------------------------------------------------------
    @api.depends('line_ids.product_id', 'line_ids.quantity')
    def _compute_line_summary(self):
        for rec in self:
            rec.line_summary = ", ".join(
                "%s x %g" % (line.product_id.display_name, line.quantity)
                for line in rec.line_ids)

    def _compute_can_respond(self):
        is_manager = self.env.user.has_group(MANAGER_GROUP)
        for rec in self:
            rec.can_respond = is_manager

    def _check_manager(self):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise UserError(_("Only an Inventory Manager can answer a "
                              "stock request."))

    @api.model
    def _get_managers(self):
        Users = self.env['res.users'].sudo()
        group = self.env.ref(MANAGER_GROUP, raise_if_not_found=False)
        users = Users.search([('groups_id', 'in', group.ids)]) if group \
            else Users
        return users.filtered(lambda u: u.active and not u.share)

    def _safe(self, method, *args):
        try:
            method(*args)
        except Exception:
            _logger.exception("accounting_so_invoice_bridge: stock request "
                              "notification %s failed - workflow unaffected.",
                              method.__name__)

    def _toast(self, user, title, message):
        if 'bus.bus' in self.env:
            self.env['bus.bus'].sudo()._sendone(
                user.partner_id, 'simple_notification',
                {'type': 'info', 'title': title,
                 'message': message, 'sticky': False})

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        is_manager = self.env.su or self.env.user.has_group(MANAGER_GROUP)
        for vals in vals_list:
            if not is_manager:
                # A salesperson can never create an already-answered request.
                for key in RESPONSE_FIELDS:
                    vals.pop(key, None)
            if vals.get('sale_order_id'):
                order = self.env['sale.order'].browse(vals['sale_order_id'])
                vals.setdefault('warehouse_id', order.warehouse_id.id)
            if not vals.get('name') or vals['name'] == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sale.stock.request') or 'New'
        records = super().create(vals_list)
        for rec in records:
            if not rec.line_ids:
                raise UserError(_("Add at least one product to request."))
            rec._safe(rec._notify_managers)
        return records

    def write(self, vals):
        if (RESPONSE_FIELDS & set(vals)
                and not self.env.su
                and not self.env.user.has_group(MANAGER_GROUP)):
            raise UserError(_("Only an Inventory Manager can answer a "
                              "stock request."))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Salesperson side
    # ------------------------------------------------------------------
    def action_cancel(self):
        for rec in self:
            if rec.state != 'requested':
                raise UserError(_("Only a request still waiting for an "
                                  "answer can be cancelled."))
            if not (self.env.user.has_group(MANAGER_GROUP)
                    or rec.salesperson_id == self.env.user):
                raise UserError(_("You can only cancel your own requests."))
        self.sudo().write({'state': 'cancel'})
        self.sudo()._close_manager_activities(_("Request cancelled."))

    # ------------------------------------------------------------------
    # Inventory Manager side
    # ------------------------------------------------------------------
    def _get_transfer_source_warehouse(self):
        """Branch the stock should come from: the other warehouse that can
        cover the most requested lines, then the one with the most stock.
        The manager can still change the locations on the transfer."""
        self.ensure_one()
        candidates = self.env['stock.warehouse'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('id', '!=', self.warehouse_id.id)])
        best, best_key = False, None
        for warehouse in candidates:
            covered, total = 0, 0.0
            for line in self.line_ids:
                free = line.product_id.sudo().with_context(
                    warehouse_id=warehouse.id).free_qty
                total += free
                if float_compare(
                        free, line.quantity,
                        precision_rounding=line.uom_id.rounding) >= 0:
                    covered += 1
            key = (covered, total)
            if best_key is None or key > best_key:
                best, best_key = warehouse, key
        return best

    def _prepare_internal_transfer_vals(self):
        self.ensure_one()
        source = self._get_transfer_source_warehouse()
        if not source:
            raise UserError(_(
                "There is no other warehouse to transfer from. Create the "
                "Internal Transfer manually and link it on this request."))
        dest = self.warehouse_id
        picking_type = source.int_type_id
        if not picking_type or not picking_type.active:
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('company_id', '=', self.company_id.id)], limit=1)
        if not picking_type:
            raise UserError(_("No Internal Transfer operation type found. "
                              "Enable it in Inventory > Configuration."))
        src_loc, dst_loc = source.lot_stock_id, dest.lot_stock_id
        return {
            'picking_type_id': picking_type.id,
            'location_id': src_loc.id,
            'location_dest_id': dst_loc.id,
            # Contact = the salesperson who made the request.
            'partner_id': self.salesperson_id.partner_id.id,
            'origin': "%s - %s" % (self.name, self.sale_order_name),
            'company_id': self.company_id.id,
            'move_ids': [(0, 0, {
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.uom_id.id,
                'location_id': src_loc.id,
                'location_dest_id': dst_loc.id,
                'company_id': self.company_id.id,
            }) for line in self.line_ids],
        }

    def action_start_internal_transfer(self):
        """Answer 'yes' AND open the prepared Internal Transfer."""
        self.ensure_one()
        self._check_manager()
        if self.state != 'requested':
            raise UserError(_("%s was already answered.", self.name))
        picking = self.env['stock.picking'].create(
            self._prepare_internal_transfer_vals())
        self.write({
            'state': 'accepted',
            'picking_id': picking.id,
            'response': self.response or _(DEFAULT_ACCEPT_TEXT),
            'responded_by': self.env.user.id,
            'responded_date': fields.Datetime.now(),
        })
        self.message_post(body=_("Internal Transfer %s created.",
                                 picking.name or picking.display_name))
        self._safe(self._notify_salesperson)
        self._close_manager_activities(_("Answered."))
        return self.action_open_picking()

    def action_open_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("No Internal Transfer is linked yet."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Internal Transfer"),
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_reject(self):
        self._check_manager()
        for rec in self:
            if rec.state != 'requested':
                raise UserError(_("%s was already answered.", rec.name))
            rec.write({
                'state': 'rejected',
                'response': rec.response or _(DEFAULT_REJECT_TEXT),
                'responded_by': self.env.user.id,
                'responded_date': fields.Datetime.now(),
            })
            rec._safe(rec._notify_salesperson)
        self._close_manager_activities(_("Answered."))

    def action_done(self):
        """Manual fallback (no transfer linked): stock has arrived."""
        self._check_manager()
        for rec in self:
            if rec.state != 'accepted':
                raise UserError(_("Only a request with a planned internal "
                                  "transfer can be marked as done."))
        self._mark_done()

    def _mark_done(self):
        """Called when the linked Internal Transfer is validated."""
        for rec in self.sudo().filtered(lambda r: r.state == 'accepted'):
            rec.state = 'done'
            rec._safe(rec._notify_salesperson)

    def _transfer_cancelled(self):
        """The linked transfer was cancelled: let the manager start over."""
        for rec in self.sudo().filtered(lambda r: r.state == 'accepted'):
            rec.write({'state': 'requested', 'picking_id': False})
            rec.message_post(body=_(
                "The Internal Transfer was cancelled. The request is open "
                "again: press Start Internal Transfer to create a new one."))

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    def _notify_managers(self):
        managers = self._get_managers() - self.env.user
        for rec in self.sudo():
            for user in managers:
                rec.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=user.id,
                    summary=_("Stock request %s", rec.name),
                    note=_("Needed in %(branch)s for order %(order)s: "
                           "%(lines)s. Press Start Internal Transfer, or "
                           "say it is not available.",
                           branch=rec.warehouse_id.name,
                           order=rec.sale_order_name,
                           lines=rec.line_summary))
                rec._toast(user, _("New stock request"),
                           _("%(lines)s for %(branch)s (%(order)s).",
                             lines=rec.line_summary,
                             branch=rec.warehouse_id.name,
                             order=rec.sale_order_name))

    def _close_manager_activities(self, feedback):
        todo = self.env.ref('mail.mail_activity_data_todo')
        for rec in self.sudo():
            rec.activity_ids.filtered(
                lambda a: a.activity_type_id == todo
                and a.user_id != rec.salesperson_id
            ).action_feedback(feedback=feedback)

    def _notify_salesperson(self):
        for rec in self.sudo():
            user = rec.salesperson_id
            if rec.state == 'done':
                text = _("Stock arrived in %(branch)s: %(lines)s. You can "
                         "now add it to the order.",
                         branch=rec.warehouse_id.name, lines=rec.line_summary)
            else:
                text = rec.response or ''
            rec.message_post(
                body=_("%(who)s answered: %(text)s",
                       who=rec.responded_by.name or _("Inventory"),
                       text=text),
                partner_ids=user.partner_id.ids,
                subtype_xmlid='mail.mt_comment')
            rec.activity_schedule(
                'mail.mail_activity_data_todo', user_id=user.id,
                summary=_("Inventory answered: %s", rec.name),
                note=text)
            rec._toast(user, _("Stock request answered"),
                       _("%(name)s: %(text)s", name=rec.name, text=text))


class SaleStockRequestLine(models.Model):
    _name = 'sale.stock.request.line'
    _description = 'Branch Stock Request Line'
    _order = 'id'

    request_id = fields.Many2one(
        'sale.stock.request', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain="[('is_storable', '=', True), ('sale_ok', '=', True)]")
    quantity = fields.Float(
        string='Quantity', required=True, default=1.0,
        digits='Product Unit of Measure')
    uom_id = fields.Many2one(
        'uom.uom', related='product_id.uom_id', string='Unit')

    _sql_constraints = [
        ('quantity_positive', 'CHECK(quantity > 0)',
         'The requested quantity must be positive.'),
    ]

    def _check_editable(self, requests):
        if self.env.su or self.env.user.has_group(MANAGER_GROUP):
            return
        if any(r.state != 'requested' for r in requests):
            raise UserError(_("The products of a request can only change "
                              "while it is waiting for an answer."))

    @api.model_create_multi
    def create(self, vals_list):
        requests = self.env['sale.stock.request'].browse(
            [v['request_id'] for v in vals_list if v.get('request_id')])
        self._check_editable(requests)
        return super().create(vals_list)

    def write(self, vals):
        self._check_editable(self.request_id)
        return super().write(vals)

    def unlink(self):
        self._check_editable(self.request_id)
        return super().unlink()
