import logging

try:
    from odoo.addons.custom_invoice_management.models.account_move import \
        cim_is_wht_tax
except ImportError:  # pragma: no cover
    def cim_is_wht_tax(tax):
        return False

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

REVIEWER_GROUP = 'accounting_so_invoice_bridge.group_sale_invoice_creator'
REVIEW_SUMMARY = 'Review payment proof & confirm invoice'


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_sale_order_ids = fields.Many2many(
        'sale.order', compute='_compute_x_sale_order_ids',
        string='Sales Orders')
    x_payment_proof_ids = fields.Many2many(
        'sale.order.payment.proof', compute='_compute_x_sale_order_ids',
        string='Payment Proofs')
    x_proof_status = fields.Selection(
        [('credit', 'Credit Order - No Proof Needed'),
         ('none', 'Not Uploaded'),
         ('rejected', 'Rejected'),
         ('pending', 'Pending'),
         ('submitted', 'Awaiting Approval'),
         ('approved', 'Approved')],
        compute='_compute_x_proof_status', string='Payment Proof')

    # --- Salesperson view: products sold + price breakdown --------------
    x_sales_line_ids = fields.Many2many(
        'account.move.line', compute='_compute_x_sales_breakdown',
        string='Products Sold',
        help='Invoice lines of the products actually sold (the Other '
             'Income line is left out).')
    x_bd_untaxed = fields.Monetary(
        compute='_compute_x_sales_breakdown', currency_field='currency_id',
        string='Untaxed Amount')
    x_bd_excise = fields.Monetary(
        compute='_compute_x_sales_breakdown', currency_field='currency_id',
        string='Excise Tax')
    x_bd_subtotal = fields.Monetary(
        compute='_compute_x_sales_breakdown', currency_field='currency_id',
        string='Subtotal')
    x_bd_other_income = fields.Monetary(
        compute='_compute_x_sales_breakdown', currency_field='currency_id',
        string='Other Income')
    x_bd_before_vat = fields.Monetary(
        compute='_compute_x_sales_breakdown', currency_field='currency_id',
        string='Before VAT')
    x_bd_vat = fields.Monetary(
        compute='_compute_x_sales_breakdown', currency_field='currency_id',
        string='VAT')
    x_bd_total_before_wht = fields.Monetary(
        compute='_compute_x_sales_breakdown', currency_field='currency_id',
        string='Total Before WHT')
    x_bd_wht = fields.Monetary(
        compute='_compute_x_sales_breakdown', currency_field='currency_id',
        string='Withholding Tax')
    x_bd_total = fields.Monetary(
        compute='_compute_x_sales_breakdown', currency_field='currency_id',
        string='Total')

    @api.model
    def _cim_is_other_income_line(self, line, service_product=None):
        """The one place that decides what "Other Income" is: the line of
        the Service Charge product that custom_invoice_management creates
        when balancing (renamed "Other Income" by
        custom_invoice_management_sale). Only if that product can't be
        found do we fall back on the label."""
        if service_product:
            return line.product_id == service_product
        label = (line.product_id.name or line.name or '').strip().lower()
        return label == 'other income'

    @api.depends('invoice_line_ids.price_subtotal',
                 'invoice_line_ids.price_total',
                 'invoice_line_ids.tax_ids',
                 'invoice_line_ids.product_id',
                 'invoice_line_ids.display_type',
                 'amount_total', 'amount_tax', 'currency_id')
    def _compute_x_sales_breakdown(self):
        """Same split as the Sales Order totals box
        (custom_invoice_management_sale._compute_cim_totals), so the order,
        the invoice page and the invoice PDF always show the same figures:
        Excise = tax that affects the base of later taxes, Withholding =
        negative tax, VAT = what is left."""
        service_product = self.env.ref(
            'custom_invoice_management.product_service_charge',
            raise_if_not_found=False)
        Tax = self.env['account.tax']
        for move in self:
            lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product')
            other = lines.filtered(
                lambda l: self._cim_is_other_income_line(l, service_product))
            sold = lines - other
            cur = move.currency_id or move.company_id.currency_id
            untaxed = sum(sold.mapped('price_subtotal'))
            other_income = sum(other.mapped('price_subtotal'))
            excise = wht = 0.0
            for line in lines.filtered('tax_ids'):
                details = line.tax_ids.compute_all(
                    line.price_unit * (1 - (line.discount or 0.0) / 100.0),
                    currency=cur, quantity=line.quantity,
                    product=line.product_id, partner=move.partner_id,
                    is_refund=move.move_type == 'out_refund')
                for detail in details['taxes']:
                    tax = Tax.browse(detail['id'])
                    if cim_is_wht_tax(tax):
                        wht += detail['amount']
                    elif tax.include_base_amount:
                        excise += detail['amount']
            excise = cur.round(excise)
            wht = cur.round(wht)
            subtotal = untaxed + excise
            before_vat = subtotal + other_income
            move.x_sales_line_ids = sold
            move.x_bd_untaxed = untaxed
            move.x_bd_excise = excise
            move.x_bd_subtotal = subtotal
            move.x_bd_other_income = other_income
            move.x_bd_before_vat = before_vat
            move.x_bd_vat = move.amount_tax - excise - wht
            move.x_bd_wht = wht
            move.x_bd_total_before_wht = move.amount_total - wht
            move.x_bd_total = move.amount_total

    # ------------------------------------------------------------------
    # Customer invoice PDF
    # ------------------------------------------------------------------
    def _get_name_invoice_report(self):
        """Customer invoices / credit notes print with the sales invoice
        template (report/report_invoice_sales.xml)."""
        self.ensure_one()
        if self.move_type in ('out_invoice', 'out_refund'):
            return 'accounting_so_invoice_bridge.report_invoice_document_sales'
        return super()._get_name_invoice_report()

    def _bridge_delivery_date(self):
        """Delivery date for the PDF: the invoice's own Delivery Date when
        Odoo has it, else the date the order was delivered."""
        self.ensure_one()
        date = self.delivery_date if 'delivery_date' in self._fields else False
        return date or self.x_sale_order_ids[:1].effective_date or False

    def _bridge_amount_in_words(self):
        self.ensure_one()
        try:
            return self.currency_id.amount_to_text(self.amount_total) or ''
        except Exception:
            return ''

    @api.depends('invoice_line_ids.sale_line_ids.order_id')
    def _compute_x_sale_order_ids(self):
        for move in self:
            orders = self.env['sale.order']
            if move.move_type in ('out_invoice', 'out_refund'):
                orders = move.invoice_line_ids.sale_line_ids.order_id
            move.x_sale_order_ids = orders
            move.x_payment_proof_ids = orders.payment_proof_ids

    @api.depends('x_sale_order_ids.x_payment_proof_status',
                 'x_sale_order_ids.x_is_credit_payment_term')
    def _compute_x_proof_status(self):
        for move in self:
            orders = move.x_sale_order_ids
            if not orders:
                move.x_proof_status = False
                continue
            statuses = {
                'credit' if o.x_is_credit_payment_term
                else o.x_payment_proof_status
                for o in orders
            }
            result = 'credit'
            for candidate in ('none', 'rejected', 'pending',
                              'submitted', 'approved'):
                if candidate in statuses:
                    result = candidate
                    break
            move.x_proof_status = result

    # ------------------------------------------------------------------
    # Navigation (invoice -> order / proofs)
    # ------------------------------------------------------------------
    def action_view_sale_orders(self):
        self.ensure_one()
        orders = self.x_sale_order_ids
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Sales Orders'),
            'res_model': 'sale.order',
        }
        if len(orders) == 1:
            action.update(view_mode='form', res_id=orders.id)
        else:
            action.update(view_mode='list,form',
                          domain=[('id', 'in', orders.ids)])
        return action

    def action_view_payment_proofs(self):
        self.ensure_one()
        list_view = self.env.ref(
            'accounting_so_invoice_bridge.view_sale_order_payment_proof_popup_list')
        form_view = self.env.ref(
            'accounting_so_invoice_bridge.view_sale_order_payment_proof_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment Proofs - %s', self.display_name),
            'res_model': 'sale.order.payment.proof',
            'view_mode': 'list,form',
            'views': [(list_view.id, 'list'), (form_view.id, 'form')],
            'domain': [('sale_order_id', 'in', self.x_sale_order_ids.ids)],
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Posting guard
    # ------------------------------------------------------------------
    def _cim_check_sale_invoice_postable(self):
        is_accountant = self.env['sale.order.payment.proof']._is_reviewer()
        status_labels = dict(
            self._fields['x_proof_status']._description_selection(self.env))
        for move in self:
            if move.move_type != 'out_invoice':
                continue
            orders = move.x_sale_order_ids
            if not orders:
                continue
            if not is_accountant:
                raise UserError(_(
                    "Only Accounting can confirm an invoice created from a "
                    "Sales Order. It has been sent to them for review."))
            for order in orders:
                if order.x_is_credit_payment_term:
                    continue
                if order.x_payment_proof_status != 'approved':
                    raise UserError(_(
                        "%(order)s cannot be invoiced yet: its payment "
                        "proof is not approved (current status: %(status)s)."
                        "\nOpen the Payment Proofs tab, then approve the "
                        "submitted proof or reject it with a reason.",
                        order=order.name,
                        status=status_labels.get(
                            order.x_payment_proof_status,
                            order.x_payment_proof_status)))

    def _post(self, soft=True):
        # Internal/automated flows (cron, sudo) are not restricted.
        if not self.env.su:
            self._cim_check_sale_invoice_postable()
        posted = super()._post(soft=soft)
        try:
            posted._cim_close_review_activities()
        except Exception:
            _logger.exception(
                "accounting_so_invoice_bridge: could not close the review "
                "activity - posting is unaffected.")
        return posted

    # ------------------------------------------------------------------
    # The one notification to Accounting
    # ------------------------------------------------------------------
    def _cim_close_review_activities(self):
        for move in self.sudo():
            activities = move.activity_ids.filtered(
                lambda a: a.summary == REVIEW_SUMMARY)
            if activities:
                activities.action_feedback(feedback=_("Invoice confirmed."))

    def _cim_notify_accounting_invoice_created(self):
        """Second (and last) hand-off to Accounting. Fired once per invoice, the moment it is created from a Sales
        Order: a To-Do activity on the invoice plus a live toast for each
        accountant. Nothing else in the workflow notifies Accounting."""
        moves = self.filtered(
            lambda m: m.x_sale_order_ids and m.move_type == 'out_invoice')
        if not moves:
            return
        Users = self.env['res.users'].sudo()
        group = self.env.ref(REVIEWER_GROUP, raise_if_not_found=False)
        recipients = Users.search([('groups_id', 'in', group.ids)]) if group else Users
        if not recipients:
            recipients = Users.search(
                [('groups_id', 'in', self.env.ref('base.group_system').ids)])
        recipients -= self.env.user
        if not recipients:
            return
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for move in moves.sudo():
            orders = move.x_sale_order_ids
            credit = all(o.x_is_credit_payment_term for o in orders)
            note = (_("Credit order: no payment proof is needed. Review the "
                      "invoice and confirm it.") if credit else
                    _("The payment proof is already approved. Check the "
                      "invoice and the accounting setup (accounts, taxes, "
                      "amounts), then confirm it."))
            for user in recipients:
                if todo:
                    move.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=user.id,
                        summary=REVIEW_SUMMARY,
                        note=note,
                    )
                if 'bus.bus' in self.env:
                    self.env['bus.bus'].sudo()._sendone(
                        user.partner_id,
                        'simple_notification',
                        {
                            'type': 'info',
                            'title': _('Invoice Ready for Review'),
                            'message': _(
                                '%(order)s for %(customer)s: draft invoice '
                                'is waiting for you.',
                                order=', '.join(orders.mapped('name')),
                                customer=move.partner_id.display_name),
                            'sticky': False,
                        },
                    )
