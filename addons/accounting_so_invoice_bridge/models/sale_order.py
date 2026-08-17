import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    can_create_invoice = fields.Boolean(
        compute='_compute_can_create_invoice',
        string='Can Create Invoice (internal)',
        help='Internal flag: true ONLY for users holding the dedicated '
             '"Can Create Invoice from Sales Order" group, or for '
             'Settings Administrators. Deliberately does NOT look at '
             'Odoo\'s native Invoicing field (Billing/Accountant) at '
             'all - that field is used for other things on some '
             'instances (e.g. it can end up set on a Sales user for '
             'unrelated reasons) and trusting it here previously let '
             'the button leak to people it should not have. The '
             'dedicated group is the single, explicit source of truth: '
             'an admin must tick it directly for a real accountant, or '
             'wire up a whole custom group via Settings > Groups > that '
             'group > Inherited Groups > add "Can Create Invoice from '
             'Sales Order" - no code change needed. Used to hide the '
             'native "Create Invoice" button for anyone else, as a '
             'second, independent check on top of the button\'s own '
             '"groups" restriction.',
    )

    payment_proof_ids = fields.One2many(
        'sale.order.payment.proof',
        'sale_order_id',
        string='Payment Proofs',
        help="Log of payment-proof files (bank transfer receipts, "
             "screenshots, etc.) the salesperson attaches once the "
             "customer has paid. Odoo's online payment integration "
             "isn't used in this flow - this is how payment confirmation "
             "is actually passed from Sales to Accounting. Only ever "
             "populated on a CONFIRMED order (state == 'sale'); see "
             "sale.order.payment.proof for the Pending -> Submitted "
             'flow - there is no approval step, since the payment '
             'already happened by the time a proof exists.',
    )
    x_has_payment_proof = fields.Boolean(
        compute='_compute_x_has_payment_proof',
        string='Payment Proof Attached',
        store=True,
        help='True once at least one payment proof line exists (in '
             'either Pending or Submitted state). Stored so it can be '
             'shown as a quick-glance column on the "Sales Orders: To '
             'Invoice" worklist without opening each order.',
    )
    x_has_submitted_payment_proof = fields.Boolean(
        compute='_compute_x_has_payment_proof',
        string='Payment Proof Submitted',
        store=True,
        help='True once at least one payment proof has been Submitted '
             'by the salesperson. Lets the worklist distinguish '
             '"something is being prepared" from "it\'s actually ready '
             'for Accounting to look at".',
    )

    payment_proof_editable = fields.Boolean(
        compute='_compute_payment_proof_editable',
        string='Payment Proof Editable (internal)',
        help='Internal flag driving the ONE payment_proof_ids list in the '
             'view (via readonly="not parent.payment_proof_editable" on '
             'its fields/buttons and create/delete="parent.payment_proof_'
             'editable" on the list itself), so only a single widget is '
             'ever rendered instead of duplicating the whole <field> '
             'block per audience.\n\n'
             'Priority order (a real-world user can easily hold more '
             'than one of these groups at once - the checks below are '
             'deliberately ordered so accounting status always wins '
             'over an incidental Sales group). This now keys off the '
             'SAME dedicated group used for the "Create Invoice" '
             'button, not Odoo\'s native Invoicing field, so a Sales '
             'user is never accidentally locked out just because their '
             'native Invoicing field happens to be set to something '
             'for unrelated reasons - and, symmetrically, someone with '
             'no other accounting access can\'t get an editable view '
             'just because that field is blank:\n'
             '  1) Settings Administrators (base.group_system) - always '
             'editable, no matter what other groups they hold.\n'
             '  2) Anyone holding the dedicated "Can Create Invoice '
             'from Sales Order" group (accounting_so_invoice_bridge.'
             'group_sale_invoice_creator) - always read-only, even if '
             'they also happen to hold a Sales group. This is what '
             'keeps a designated accountant who also has Sales access '
             'from seeing the editable "Add a line" version, and, just '
             'as important, from being caught by the Sales-only read '
             'ir.rule that would otherwise hide every proof that is '
             'not their own.\n'
             '  3) Otherwise, editable only for Salespeople '
             '(sales_team.group_sale_salesman).\n'
             'Everyone else (no relevant group at all) gets neither - '
             'the page itself is already hidden for them via its own '
             '"groups" attribute, so this only matters for the small '
             'number of groups the page is shown to. Note that a '
             'native Billing/Accountant user with no dedicated group '
             'still gets read-only access to the tab through their own '
             'ir.model.access.csv/ir.rule entries (see security.xml) - '
             'this field only controls whether the widget looks '
             'editable, not whether the record is visible at all.',
    )

    x_is_credit_payment_term = fields.Boolean(
        compute='_compute_x_is_credit_payment_term',
        string='Credit Payment Term (internal)',
        help='True only when the selected Payment Terms\' name contains '
             'the word "credit" (case-insensitive), e.g. "Credit 30 '
             'Days". This is a simple name check, not an inspection of '
             'the term\'s installment lines - so it relies on credit '
             'payment terms in this database being named with the word '
             '"credit" somewhere in them. If no payment term is selected '
             'yet, or its name doesn\'t contain "credit", this is False. '
             'Used to hide (and un-require) the Payment Proof field for '
             'credit orders only - the field stays visible/required by '
             'default (including when no payment term has been picked '
             'yet), since there is no reason to hide/un-require it '
             'unless we can positively tell the term is a credit term.',
    )

    @api.depends('payment_proof_ids.state')
    def _compute_x_has_payment_proof(self):
        for order in self:
            order.x_has_payment_proof = bool(order.payment_proof_ids)
            order.x_has_submitted_payment_proof = bool(
                order.payment_proof_ids.filtered(
                    lambda p: p.state == 'submitted'))

    @api.depends('payment_term_id', 'payment_term_id.name')
    def _compute_x_is_credit_payment_term(self):
        for order in self:
            term = order.payment_term_id
            order.x_is_credit_payment_term = bool(
                term and 'credit' in (term.name or '').lower()
            )

    @api.depends_context('uid')
    def _compute_payment_proof_editable(self):
        user = self.env.user
        if user.has_group('base.group_system'):
            editable = True
        elif user.has_group(
                'accounting_so_invoice_bridge.group_sale_invoice_creator'):
            # The dedicated "accountant" group wins over an incidental
            # Sales group - a designated accountant who also has some
            # Sales access must still get the read-only rendering.
            editable = False
        else:
            editable = user.has_group('sales_team.group_sale_salesman')
        for order in self:
            order.payment_proof_editable = editable

    @api.depends_context('uid')
    def _compute_can_create_invoice(self):
        allowed = (
            self.env.user.has_group(
                'accounting_so_invoice_bridge.group_sale_invoice_creator')
            or self.env.user.has_group('base.group_system')
        )
        for order in self:
            order.can_create_invoice = allowed

    def action_view_payment_proofs(self):
        """Quick-glance popup (read-only) so a user can see/download every
        payment-proof file on this order without switching to the
        'Payment Proofs' tab first. Triggered from the header stat
        button. Editing still only happens in that tab, gated by the
        usual payment_proof_editable/ir.rule rules - this popup is a
        pure viewer, always create=False/edit=False, regardless of who
        opens it."""
        self.ensure_one()
        list_view = self.env.ref(
            'accounting_so_invoice_bridge.'
            'view_sale_order_payment_proof_popup_list')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment Proofs - %s', self.name),
            'res_model': 'sale.order.payment.proof',
            'view_mode': 'list,form',
            'views': [(list_view.id, 'list'), (False, 'form')],
            'domain': [('sale_order_id', '=', self.id)],
            'target': 'new',
        }

    def action_confirm(self):
        """Standard Odoo hook: called the moment a quotation is confirmed
        into a Sales Order (state -> 'sale'). super() first, so a
        notification only ever fires for an order that genuinely got
        confirmed - if super() raises (e.g. a stock/tax validation
        error) nothing gets sent.

        The notification step itself is deliberately best-effort: it
        runs in its own try/except so that ANY problem sending it (a
        bus/mail configuration quirk, a missing group on a fresh
        database, an Odoo-version API difference, etc.) can never turn
        into a failed order confirmation. Confirming the order is the
        actual business action; the toast is a courtesy on top of it,
        not a precondition for it. Logged, not swallowed silently, so
        it's still visible to an admin checking the server log."""
        res = super().action_confirm()
        for order in self:
            try:
                order._notify_accounting_order_confirmed()
            except Exception:
                _logger.exception(
                    "accounting_so_invoice_bridge: failed to notify "
                    "Accounting that %s was confirmed - the order "
                    "confirmation itself is unaffected.", order.name)
        return res

    def _notify_accounting_order_confirmed(self):
        """Real-time toast telling Accounting a Sales Order is ready for
        them - they're the ones who'll create the invoice and record the
        payment from here, so they're the audience, not Sales.

        Uses Odoo's own 'simple_notification' bus message type - the
        exact same mechanism core Odoo already uses for its built-in
        toasts elsewhere (e.g. Discuss/Calendar reminders). The web
        client's listener for this message type ships as part of the
        'bus'/'mail' JavaScript already loaded for every logged-in user,
        so nothing needs to be added or configured on the frontend for
        this to show up - firing the bus message server-side is the
        entire implementation.

        This is intentionally independent of - and in addition to -
        binget_dashboard's own notification bell/badge, which picks up
        newly-confirmed, not-yet-invoiced orders on its own next refresh
        (see get_notifications() in that module) for anyone who missed
        the live toast (was offline, dashboard not open, etc.). Neither
        mechanism depends on the other, so this module works exactly
        the same with or without binget_dashboard installed.
        """
        self.ensure_one()
        if 'bus.bus' not in self.env:
            return

        domain = [('groups_id', 'in', [
            self.env.ref('account.group_account_invoice').id,
            self.env.ref('base.group_system').id,
        ])]
        group_creator = self.env.ref(
            'accounting_so_invoice_bridge.group_sale_invoice_creator',
            raise_if_not_found=False)
        if group_creator:
            domain = [('groups_id', 'in', [
                self.env.ref('account.group_account_invoice').id,
                self.env.ref('base.group_system').id,
                group_creator.id,
            ])]
        recipients = self.env['res.users'].sudo().search(domain)
        # Don't toast whoever just confirmed the order themselves - they
        # already know, they're the one who clicked Confirm.
        recipients = recipients - self.env.user
        if not recipients:
            return

        for partner in recipients.partner_id:
            self.env['bus.bus'].sudo()._sendone(
                partner,
                'simple_notification',
                {
                    'type': 'success',
                    'title': _('Sales Order Confirmed'),
                    'message': _(
                        '%(order)s for %(customer)s is confirmed and '
                        'ready for invoicing.',
                        order=self.name,
                        customer=self.partner_id.display_name,
                    ),
                    'sticky': False,
                },
            )
