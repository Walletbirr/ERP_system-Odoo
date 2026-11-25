from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero, float_compare


class LCSettlementLine(models.Model):
    _name = 'lc.settlement.line'
    _description = 'LC Settlement Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date asc'

    # =========================================================
    # LINKAGE
    # =========================================================
    lc_id = fields.Many2one(
        'lc.management',
        string="Letter of Credit",
        required=True,
        ondelete='cascade'
    )
    company_currency_id = fields.Many2one(
        related='lc_id.company_currency_id',
        string="Company Currency",
        readonly=True
    )
    lc_currency_id = fields.Many2one(
        related='lc_id.currency_id',
        string="LC Currency",
        readonly=True
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string="Purchase Order",
        readonly=True
    )
    shipment_id = fields.Many2one(
        'shipment.tracking',
        string="Shipment",
        readonly=True,
        help="The shipment whose arrival at final destination triggered this settlement line."
    )
    vendor_bill_id = fields.Many2one(
        'account.move',
        string="Vendor Bill",
        readonly=True,
        help="Optional reference to the vendor bill for this Purchase Order, if one exists "
             "by the time this line is viewed. Not used to size the settlement amount."
    )
    parent_settlement_line_id = fields.Many2one(
        'lc.settlement.line',
        string="Split From",
        readonly=True,
        help="If this line was created by splitting a partial amount off another "
             "settlement line, this points to that original line."
    )
    split_line_ids = fields.One2many(
        'lc.settlement.line', 'parent_settlement_line_id',
        string="Split Into",
        readonly=True,
    )
    is_root_line = fields.Boolean(
        string="Is Root Line",
        compute='_compute_is_root_line',
        store=True,
        help="True for the original line auto-created when the shipment arrived "
             "(i.e. it has no parent). Used to show exactly one summary row per "
             "Purchase Order in list views, regardless of how many partial "
             "tranches it was split into."
    )
    po_total_settled = fields.Monetary(
        string="Total Settled (this PO)",
        currency_field='lc_currency_id',
        compute='_compute_po_rollup',
        store=True,
        help="Sum of amount_to_settle across every CONFIRMED tranche for this PO "
             "(this line plus all its splits)."
    )
    po_total_amount = fields.Monetary(
        string="PO Total",
        currency_field='lc_currency_id',
        compute='_compute_po_rollup',
        store=True,
        help="The full original amount for this PO (this line's amount plus all "
             "its splits' amounts, confirmed or still in draft)."
    )
    po_remaining_to_settle = fields.Monetary(
        string="Remaining to Settle (this PO)",
        currency_field='lc_currency_id',
        compute='_compute_po_rollup',
        store=True,
    )
    po_tranche_count = fields.Integer(
        string="Number of Tranches",
        compute='_compute_po_rollup',
        store=True,
    )
    po_is_fully_settled = fields.Boolean(
        string="Fully Settled",
        compute='_compute_po_rollup',
        store=True,
    )
    po_settlement_status = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
    ], string="Settlement Status",
        compute='_compute_po_rollup',
        store=True,
        help="Draft: nothing settled yet for this PO. Pending: at least one "
             "partial payment has been confirmed but the PO isn't fully paid "
             "off yet. Completed: every tranche for this PO has been confirmed "
             "and there is nothing left to settle."
    )
    all_tranche_ids = fields.Many2many(
        'lc.settlement.line',
        compute='_compute_po_rollup',
        string="All Tranches (this PO)",
        help="This line plus every line it was split into - the complete picture "
             "of how this PO's settlement was paid, in order.",
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted for Payment'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, readonly=True, tracking=True)

    # =========================================================
    # PURCHASE OFFICER -> ACCOUNTANT PAYMENT APPROVAL WORKFLOW
    # =========================================================
    requested_by_id = fields.Many2one(
        'res.users', string="Payment Requested By", readonly=True
    )
    request_date = fields.Datetime(string="Requested On", readonly=True)
    assigned_accountant_id = fields.Many2one(
        'res.users', string="Sent To", readonly=True,
        help="The accountant asked to review and approve this payment."
    )
    approved_by_id = fields.Many2one(
        'res.users', string="Approved By", readonly=True
    )
    approved_date = fields.Datetime(string="Approved On", readonly=True)

    # =========================================================
    # AMOUNT BEING SETTLED (THIS TRANCHE)
    # =========================================================
    amount_to_settle = fields.Monetary(
        string="Amount to Settle (this tranche)",
        currency_field='lc_currency_id',
        required=True,
        readonly=True,
        help="The portion of the PO total being settled in this specific tranche. "
             "Starts as the full PO total when the shipment arrives; can be split "
             "into multiple smaller tranches for partial payments, each confirmed "
             "independently with its own bank fee, VAT, and rate."
    )

    # =========================================================
    # FEES / VAT (PER TRANCHE - CAN DIFFER EACH TIME)
    # =========================================================
    settlement_fee = fields.Monetary(
        string="Settlement Fee",
        currency_field='company_currency_id'
    )
    settlement_fee_account_id = fields.Many2one(
        'account.account',
        string="Settlement Fee Account"
    )
    settlement_vat_amount = fields.Monetary(
        string="Settlement VAT Amount",
        currency_field='company_currency_id'
    )
    settlement_vat_account_id = fields.Many2one(
        'account.account',
        string="Settlement VAT Account"
    )
    settlement_rate = fields.Float(
        string="Settlement Rate",
        digits=(12, 6)
    )
    settlement_date = fields.Date(
        string="Settlement Date",
        default=fields.Date.today
    )

    # =========================================================
    # SETTLEMENT VALUE AT THE NEW RATE, LESS MARGIN ALREADY PAID
    # =========================================================
    # The margin was paid to the bank at opening (and posted to the LC's GIT
    # account at the opening rate). At settlement the bank values the tranche
    # at the NEW rate and deducts the margin already held; only the balance
    # is paid now and posted to GIT. So the total cost carried in GIT for the
    # tranche equals its value at the settlement rate.
    margin_applied_this_line = fields.Monetary(
        string="Margin Already Paid (this tranche)",
        currency_field='company_currency_id',
        compute='_compute_margin_applied_this_line',
        store=True,
        help="This tranche's proportional share of the margin paid at opening "
             "(LC margin x tranche amount / LC amount), capped so the sum over "
             "all tranches never exceeds the margin paid."
    )
    settlement_value_company = fields.Monetary(
        string="Value at Settlement Rate",
        currency_field='company_currency_id',
        compute='_compute_settlement_balance',
        help="Amount to settle x settlement rate."
    )
    balance_to_pay_company = fields.Monetary(
        string="Balance Paid Now (to GIT)",
        currency_field='company_currency_id',
        compute='_compute_settlement_balance',
        help="Value at the settlement rate, less the margin already paid at "
             "opening. This is what leaves the bank for the goods in this "
             "tranche and is posted to the LC's GIT account."
    )

    # =========================================================
    # ACCOUNTING MOVE PRODUCED ON CONFIRM
    # =========================================================
    settlement_move_id = fields.Many2one(
        'account.move', string="Settlement Entry", readonly=True
    )

    def _get_effective_rate(self):
        """The rate this tranche is settled at: the one typed on the line, or
        the current system rate for its settlement date if left empty."""
        self.ensure_one()
        if not float_is_zero(self.settlement_rate, precision_digits=6):
            return self.settlement_rate
        lc = self.lc_id
        return self.env['res.currency']._get_conversion_rate(
            lc.currency_id,
            self.env.company.currency_id,
            self.env.company,
            self.settlement_date or fields.Date.today(),
        )

    @api.depends('amount_to_settle', 'settlement_rate', 'settlement_date',
                 'margin_applied_this_line', 'lc_id.currency_id')
    def _compute_settlement_balance(self):
        for line in self:
            if not line.lc_id:
                line.settlement_value_company = 0.0
                line.balance_to_pay_company = 0.0
                continue
            rate = line._get_effective_rate()
            value = line.company_currency_id.round(line.amount_to_settle * rate)
            line.settlement_value_company = value
            line.balance_to_pay_company = line.company_currency_id.round(
                value - line.margin_applied_this_line
            )

    @api.depends(
        'amount_to_settle',
        'state',
        'lc_id.amount',
        'lc_id.margin_amount_company_currency',
        'lc_id.settlement_line_ids.amount_to_settle',
        'lc_id.settlement_line_ids.state',
    )
    def _compute_margin_applied_this_line(self):
        for line in self:
            lc = line.lc_id

            if (
                not lc
                or line.state == 'cancelled'
                or float_is_zero(lc.amount, precision_rounding=lc.currency_id.rounding or 0.01)
            ):
                line.margin_applied_this_line = 0.0
                continue

            # Proportional share of the margin this tranche represents.
            theoretical = lc.margin_amount_company_currency * (line.amount_to_settle / lc.amount)

            # Cap at what is still unapplied, worked out from the sibling
            # CONFIRMED lines (excluding self by id) so the result is the same
            # however many times or in whatever order Odoo recomputes it.
            others = lc.settlement_line_ids.filtered(
                lambda l: l.id != line.id and l.state == 'confirmed'
            )
            applied_by_others = min(
                sum(lc.margin_amount_company_currency * (l.amount_to_settle / lc.amount)
                    for l in others),
                lc.margin_amount_company_currency,
            )
            remaining = max(lc.margin_amount_company_currency - applied_by_others, 0.0)
            line.margin_applied_this_line = min(theoretical, remaining)

    def _prepare_settlement_entries(self):
        """Single source of truth for the settlement journal entry, used by
        both the preview and the posting so they can never disagree.

        Returns a list of rows {label, account, debit, credit}; the bank row
        is last and balances the entry. Debits go to the LC's GIT account for
        the balance of the goods and for the fee, and to the VAT account."""
        self.ensure_one()
        lc = self.lc_id
        rows = []

        balance = self.balance_to_pay_company
        if not float_is_zero(balance, precision_digits=2):
            rows.append({
                'label': f"LC Settlement Balance - {lc.name}",
                'account': lc.opening_fee_account_id,
                'debit': max(balance, 0.0),
                'credit': max(-balance, 0.0),
            })
        if not float_is_zero(self.settlement_fee, precision_digits=2):
            rows.append({
                'label': f"LC Settlement Fee - {lc.name}",
                'account': self.settlement_fee_account_id,
                'debit': self.settlement_fee,
                'credit': 0.0,
            })
        if self.settlement_vat_account_id and not float_is_zero(
            self.settlement_vat_amount, precision_digits=2
        ):
            rows.append({
                'label': f"LC Settlement VAT - {lc.name}",
                'account': self.settlement_vat_account_id,
                'debit': self.settlement_vat_amount,
                'credit': 0.0,
            })

        net = sum(r['debit'] for r in rows) - sum(r['credit'] for r in rows)
        if rows and not float_is_zero(net, precision_digits=2):
            rows.append({
                'label': f"LC Settlement - {lc.name}",
                'account': lc.bank_journal_id.default_account_id,
                'debit': max(-net, 0.0),
                'credit': max(net, 0.0),
            })
        return rows

    # =========================================================
    # ROOT LINE + PO-LEVEL ROLLUP (for the per-PO summary view)
    # =========================================================
    @api.depends('parent_settlement_line_id')
    def _compute_is_root_line(self):
        for line in self:
            line.is_root_line = not bool(line.parent_settlement_line_id)

    def _get_root_line(self):
        """Walks up parent_settlement_line_id to find the original line
        for this PO, regardless of how many splits deep this one is."""
        self.ensure_one()
        line = self
        seen = set()
        while line.parent_settlement_line_id and line.id not in seen:
            seen.add(line.id)
            line = line.parent_settlement_line_id
        return line

    @api.depends(
        'parent_settlement_line_id',
        'parent_settlement_line_id.split_line_ids.amount_to_settle',
        'parent_settlement_line_id.split_line_ids.state',
        'split_line_ids.amount_to_settle',
        'split_line_ids.state',
        'split_line_ids.split_line_ids',
        'amount_to_settle',
        'state',
    )
    # def _compute_po_rollup(self):
    #     for line in self:
    #         root = line._get_root_line()

    #         # Gather every tranche for this PO: the root plus all its
    #         # splits, recursively (in case a split was itself split again).
    #         all_tranches = root
    #         frontier = root.split_line_ids
    #         seen_ids = {root.id}
    #         while frontier:
    #             new_frontier = self.env['lc.settlement.line']
    #             for t in frontier:
    #                 if t.id not in seen_ids:
    #                     all_tranches |= t
    #                     seen_ids.add(t.id)
    #                     new_frontier |= t.split_line_ids
    #             frontier = new_frontier

    #         confirmed = all_tranches.filtered(lambda t: t.state == 'confirmed')
    #         cancelled_excluded = all_tranches.filtered(lambda t: t.state != 'cancelled')

    #         line.all_tranche_ids = all_tranches
    #         line.po_total_settled = sum(confirmed.mapped('amount_to_settle'))
    #         line.po_total_amount = sum(cancelled_excluded.mapped('amount_to_settle'))
    #         line.po_remaining_to_settle = max(line.po_total_amount - line.po_total_settled, 0.0)
    #         line.po_tranche_count = len(all_tranches.filtered(lambda t: t.state != 'cancelled'))

    #         lc_currency = line.lc_id.currency_id
    #         line.po_is_fully_settled = bool(cancelled_excluded) and float_is_zero(
    #             line.po_remaining_to_settle,
    #             precision_rounding=lc_currency.rounding if lc_currency else 0.01
    #         )

    #         # ---- Settlement status: draft / pending / completed ----
    #         if line.po_is_fully_settled:
    #             line.po_settlement_status = 'completed'
    #         elif confirmed:
    #             # At least one tranche confirmed, but not all of it settled yet.
    #             line.po_settlement_status = 'pending'
    #         else:
    #             line.po_settlement_status = 'draft'
    @api.depends(
    'parent_settlement_line_id',
    'parent_settlement_line_id.split_line_ids.amount_to_settle',
    'parent_settlement_line_id.split_line_ids.state',
    'split_line_ids.amount_to_settle',
    'split_line_ids.state',
    'split_line_ids.split_line_ids',
    'amount_to_settle',
    'state',
    )
    def _compute_po_rollup(self):
        for line in self:
            root = line._get_root_line()
            all_tranches = root
            frontier = root.split_line_ids
            seen_ids = {root.id}
            while frontier:
                new_frontier = self.env['lc.settlement.line']
                for t in frontier:
                    if t.id not in seen_ids:
                        all_tranches |= t
                        seen_ids.add(t.id)
                        new_frontier |= t.split_line_ids
                frontier = new_frontier

            # Once the root has been split, it's a permanent zero-balance
            # anchor - every real tranche now lives on a non-root descendant.
            # Drop it from the rollups/table entirely. If it was never split,
            # it's still the one and only real tranche, so keep it.
            if root.split_line_ids:
                real_tranches = all_tranches - root
            else:
                real_tranches = all_tranches

            confirmed = real_tranches.filtered(lambda t: t.state == 'confirmed')
            cancelled_excluded = real_tranches.filtered(lambda t: t.state != 'cancelled')

            # Drafts first (they're what needs your attention), then confirmed,
            # then cancelled - each group still oldest-first internally.
            STATE_ORDER = {'draft': 0, 'confirmed': 1, 'cancelled': 2}
            sorted_tranches = real_tranches.sorted(
                key=lambda t: (STATE_ORDER.get(t.state, 9), t.create_date or fields.Datetime.now())
            )
            line.all_tranche_ids = sorted_tranches

            line.po_total_settled = sum(confirmed.mapped('amount_to_settle'))
            line.po_total_amount = sum(cancelled_excluded.mapped('amount_to_settle'))
            line.po_remaining_to_settle = max(line.po_total_amount - line.po_total_settled, 0.0)
            line.po_tranche_count = len(real_tranches.filtered(lambda t: t.state != 'cancelled'))

            lc_currency = line.lc_id.currency_id
            line.po_is_fully_settled = bool(cancelled_excluded) and float_is_zero(
                line.po_remaining_to_settle,
                precision_rounding=lc_currency.rounding if lc_currency else 0.01
            )

            if line.po_is_fully_settled:
                line.po_settlement_status = 'completed'
            elif confirmed:
                line.po_settlement_status = 'pending'
            else:
                line.po_settlement_status = 'draft'
    def _check_ready_for_settlement(self):
        """Shared readiness checks used by both the purchase officer's
        submit-for-approval step and the accountant's post step, so the two
        can never disagree about what counts as 'ready'."""
        self.ensure_one()
        line = self
        if not line.purchase_order_id:
            raise ValidationError("This settlement line has no linked Purchase Order.")
        if line.purchase_order_id.state not in ('purchase', 'done'):
            raise ValidationError(f"Purchase Order {line.purchase_order_id.name} is not confirmed.")
        if line.shipment_id and line.shipment_id.state != 'arrived':
            raise ValidationError(
                f"Shipment {line.shipment_id.reference} is no longer marked as Arrived."
            )
        if float_is_zero(line.settlement_fee, precision_digits=2):
            raise ValidationError("Settlement Fee must be greater than zero.")
        if not line.settlement_fee_account_id:
            raise ValidationError(
                "Please select a settlement fee account. If it doesn't exist yet in the "
                "Chart of Accounts, use 'Request Account Setup' on the LC to notify the accountant."
            )
        if not line.settlement_vat_account_id and not float_is_zero(
            line.settlement_vat_amount, precision_digits=2
        ):
            raise ValidationError("Please select a settlement VAT account.")
        if not line.settlement_date:
            raise ValidationError("Please enter a settlement date.")
        if float_is_zero(line.settlement_vat_amount, precision_digits=2):
            raise ValidationError("Settlement VAT Amount must be greater than zero.")

    def _is_lc_accountant(self):
        return (
            self.env.user.has_group('lc_management.group_lc_accountant')
            or self.env.user.has_group('account.group_account_manager')
        )

    def action_request_payment(self):
        """Purchase Officer step: validates the tranche is ready, then lets
        them pick which accountant should review and approve the payment."""
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError("Only draft settlement lines can be submitted for payment.")
        self._check_ready_for_settlement()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Payment Request',
            'res_model': 'lc.settlement.payment.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_settlement_line_id': self.id},
        }

    def _send_payment_request(self, accountant, note=None):
        self.ensure_one()
        self.write({
            'state': 'submitted',
            'requested_by_id': self.env.user.id,
            'request_date': fields.Datetime.now(),
            'assigned_accountant_id': accountant.id if accountant else False,
        })
        self._notify_accountant_for_payment(accountant, note)

    def _notify_accountant_for_payment(self, accountant, note=None):
        for line in self:
            partner_ids = accountant.partner_id.ids if accountant else []
            line.message_subscribe(partner_ids=partner_ids)
            body = (
                f"Payment requested by {line.requested_by_id.name} for "
                f"<b>{line.purchase_order_id.name or line.lc_id.name}</b>: "
                f"{line.amount_to_settle:,.2f} {line.lc_currency_id.name}. "
                f"Awaiting accountant approval."
            )
            if note:
                body += f"<br/>Note: {note}"
            line.message_post(body=body, partner_ids=partner_ids)
            if accountant:
                line.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=f"Approve LC payment - {line.lc_id.name}",
                    note=note or "A purchase officer submitted a settlement payment for your approval.",
                    user_id=accountant.id,
                )
                self.env['bus.bus']._sendone(accountant.partner_id, 'simple_notification', {
                    'type': 'info',
                    'title': 'LC Payment Request',
                    'message': (
                        f"{line.requested_by_id.name} needs approval on a payment for "
                        f"{line.purchase_order_id.name or line.lc_id.name}: "
                        f"{line.amount_to_settle:,.2f} {line.lc_currency_id.name}."
                    ),
                    'sticky': True,
                    'className': 'o_lc_request_notification',
                })
            self.env.user._bus_send('simple_notification', {
                'type': 'success',
                'title': 'Request Sent',
                'message': (
                    f"Payment request for {line.purchase_order_id.name or line.lc_id.name} "
                    f"sent to {accountant.name}." if accountant else
                    f"Payment request sent, but no accountant was selected."
                ),
            })

    def action_confirm_with_preview(self):
        """Validates this line exactly as action_confirm would, builds a
        plain-text preview of the settlement entry about to post, and opens
        a confirmation wizard. Posting only
        happens if the user confirms in that wizard."""
        self.ensure_one()
        line = self
        lc = line.lc_id

        # Run the same checks action_confirm runs, so the preview can never
        # show a wizard for something that would then fail to post.
        if not line._is_lc_accountant():
            raise ValidationError("Only an Accountant can approve and post this payment.")
        if line.state != 'submitted':
            raise ValidationError(
                "This settlement line must be submitted for payment approval first "
                "(use 'Send Payment Request')."
            )
        if not line.purchase_order_id:
            raise ValidationError("This settlement line has no linked Purchase Order.")
        if line.purchase_order_id.state not in ('purchase', 'done'):
            raise ValidationError(f"Purchase Order {line.purchase_order_id.name} is not confirmed.")
        if line.shipment_id and line.shipment_id.state != 'arrived':
            raise ValidationError(
                f"Shipment {line.shipment_id.reference} is no longer marked as Arrived."
            )
        if float_is_zero(line.settlement_fee, precision_digits=2):
            raise ValidationError("Settlement Fee must be greater than zero.")

        if not line.settlement_fee_account_id:
            raise ValidationError("Please select a settlement fee account.")
        if not line.settlement_vat_account_id and not float_is_zero(
            line.settlement_vat_amount, precision_digits=2
        ):
            raise ValidationError("Please select a settlement VAT account.")
        if not line.settlement_date:
            raise ValidationError("Please enter a settlement date.")

        if float_is_zero(line.settlement_vat_amount, precision_digits=2):
            raise ValidationError("Settlement VAT Amount must be greater than zero.")

        settlement_rate = line.settlement_rate
        if float_is_zero(settlement_rate, precision_digits=6):
            company_currency = lc.env.company.currency_id
            settlement_rate = self.env['res.currency']._get_conversion_rate(
                lc.currency_id, company_currency, lc.env.company,
                line.settlement_date or fields.Date.today()
            )

        bank_account = lc.bank_journal_id.default_account_id
        if not bank_account:
            raise ValidationError("Bank journal missing default account.")

        other_lines = lc.settlement_line_ids.filtered(
            lambda l: l.id != line.id and l.state == 'confirmed'
        )
        total_settled_if_confirmed = sum(other_lines.mapped('amount_to_settle')) + line.amount_to_settle
        if float_compare(total_settled_if_confirmed, lc.amount, precision_rounding=lc.currency_id.rounding) > 0:
            raise ValidationError("This settlement would exceed the LC amount.")

        if not lc.opening_fee_account_id:
            raise ValidationError("The LC has no GIT Account. Set it on the LC first.")

        cur = lc.company_currency_id.name
        lc_cur = lc.currency_id.name
        rate = line._get_effective_rate()
        preview_lines = [
            f"Value at settlement rate: {line.amount_to_settle:,.2f} {lc_cur} x {rate:,.6f} = "
            f"{line.settlement_value_company:,.2f} {cur}",
            f"Less margin already paid at opening: {line.margin_applied_this_line:,.2f} {cur}",
            f"Balance paid now: {line.balance_to_pay_company:,.2f} {cur}",
            "",
            "Settlement Entry:",
        ]
        rows = line._prepare_settlement_entries()
        if rows:
            for r in rows:
                if not float_is_zero(r['debit'], precision_digits=2):
                    preview_lines.append(
                        f"  Debit  {r['account'].name} ({r['label']}): {r['debit']:,.2f} {cur}"
                    )
                if not float_is_zero(r['credit'], precision_digits=2):
                    preview_lines.append(
                        f"  Credit {r['account'].name} ({r['label']}): {r['credit']:,.2f} {cur}"
                    )
        else:
            preview_lines.append("  No accounting entry will be posted (balance, fee and VAT are all zero).")

        wizard = self.env['lc.settlement.confirm.wizard'].create({
            'settlement_line_id': line.id,
            'preview_text': "\n".join(preview_lines),
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirm Settlement',
            'res_model': 'lc.settlement.confirm.wizard',
            'view_mode': 'form',
            'target': 'new',
            'res_id': wizard.id,
        }

    # =========================================================
    # CONFIRM: VALIDATE + POST BOTH MOVES
    # =========================================================
    def action_confirm(self):
        for line in self:
            lc = line.lc_id

            if not line._is_lc_accountant():
                raise ValidationError("Only an Accountant can approve and post this payment.")
            if line.state != 'submitted':
                raise ValidationError(
                    "This settlement line must be submitted for payment approval first "
                    "(use 'Send Payment Request')."
                )

            # ===================== PURCHASE ORDER VALIDATION =====================
            # Restored from the original action_settle: the PO behind this
            # settlement must actually be confirmed, not draft/cancelled.
            if not line.purchase_order_id:
                raise ValidationError("This settlement line has no linked Purchase Order.")

            if line.purchase_order_id.state not in ('purchase', 'done'):
                raise ValidationError(
                    f"Purchase Order {line.purchase_order_id.name} is not confirmed."
                )

            # ===================== SHIPMENT VALIDATION =====================
            # This line should only ever exist once its shipment has arrived
            # (that's the trigger that creates it - see lc.py
            # _create_draft_settlement_line_for_shipment). This check is a
            # defensive guard against an inconsistent state, e.g. if the
            # shipment was somehow reset after the line was created.
            if line.shipment_id and line.shipment_id.state != 'arrived':
                raise ValidationError(
                    f"Shipment {line.shipment_id.reference} is no longer marked as Arrived. "
                    f"Settlement cannot be confirmed until the shipment status is corrected."
                )

            # ===================== VALIDATIONS =====================
            if float_is_zero(line.amount_to_settle, precision_rounding=lc.currency_id.rounding):
                raise ValidationError("Amount to settle must be greater than zero.")

            if not line.settlement_fee_account_id:
                raise ValidationError("Please select a settlement fee account.")

            if not line.settlement_vat_account_id and not float_is_zero(
                line.settlement_vat_amount, precision_digits=2
            ):
                raise ValidationError("Please select a settlement VAT account.")

            if not line.settlement_date:
                raise ValidationError("Please enter a settlement date.")

            if float_is_zero(line.settlement_rate, precision_digits=6):
                company_currency = lc.env.company.currency_id
                line.settlement_rate = self.env['res.currency']._get_conversion_rate(
                    lc.currency_id,
                    company_currency,
                    lc.env.company,
                    line.settlement_date or fields.Date.today()
                )

            bank_account = lc.bank_journal_id.default_account_id
            if not bank_account:
                raise ValidationError("Bank journal missing default account.")

            # Don't let this tranche push total settled past the LC amount
            other_lines = lc.settlement_line_ids.filtered(
                lambda l: l.id != line.id and l.state == 'confirmed'
            )
            total_settled_if_confirmed = sum(other_lines.mapped('amount_to_settle')) + line.amount_to_settle
            if float_compare(total_settled_if_confirmed, lc.amount, precision_rounding=lc.currency_id.rounding) > 0:
                raise ValidationError(
                    f"This settlement would exceed the LC amount.\n"
                    f"LC Amount: {lc.amount}, Already settled: {sum(other_lines.mapped('amount_to_settle'))}, "
                    f"This tranche: {line.amount_to_settle}"
                )

            # ===================== SETTLEMENT ENTRY =====================
            # Debit GIT for the balance of the goods (value at the settlement
            # rate less the margin already paid at opening) and for the fee,
            # debit VAT, credit the bank - one entry, same builder as the
            # preview.
            if not lc.opening_fee_account_id:
                raise ValidationError("The LC has no GIT Account. Set it on the LC first.")

            rows = line._prepare_settlement_entries()
            if rows:
                settlement_move = self.env['account.move'].create({
                    'move_type': 'entry',
                    'journal_id': lc.bank_journal_id.id,
                    'ref': f"LC Settlement - {lc.name}",
                    'line_ids': [
                        (0, 0, {
                            'name': r['label'],
                            'account_id': r['account'].id,
                            'debit': r['debit'],
                            'credit': r['credit'],
                        })
                        for r in rows
                    ],
                })
                settlement_move.action_post()
                line.settlement_move_id = settlement_move.id

            line.write({
                'state': 'confirmed',
                'approved_by_id': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })

            # Recompute dependent fields then check if the LC can move to 'settled'
            lc._compute_paid_amount()
            lc._compute_remaining_amount()
            lc._refresh_settlement_state()
            # This tranche is now confirmed - check whether the whole PO
            # (root + every split) is now fully settled. If so, the root
            # (which has nothing of its own left to confirm) can finally
            # be marked confirmed too - not before, since it shouldn't
            # claim "done" while any sibling tranche still owes money.
            root = line._get_root_line()
            if root != line and root.state == 'draft' and root.po_is_fully_settled:
                root.state = 'confirmed'

    def action_cancel_line(self):
        """Reverse a confirmed line's moves and mark it cancelled. Used by LC cancellation."""
        for line in self:
            if line.state != 'confirmed':
                line.state = 'cancelled'
                continue

            if line.settlement_move_id:
                line.lc_id._reverse_move(line.settlement_move_id)

            line.state = 'cancelled'

    def action_open_split_wizard(self):
        """Opens a small wizard asking how much of this draft line's
        remaining amount should be split off into its own tranche, so a
        partial payment can be confirmed independently with its own fee/
        VAT/rate, while the rest stays in this line until paid off."""
        self.ensure_one()

        if self.state != 'draft':
            raise ValidationError("Only a draft settlement line can be split.")

        wizard = self.env['lc.settlement.split.wizard'].create({
            'settlement_line_id': self.id,
            'split_amount': self.amount_to_settle,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Split Into Partial Settlement',
            'res_model': 'lc.settlement.split.wizard',
            'view_mode': 'form',
            'target': 'new',
            'res_id': wizard.id,
        }

    # def _split_off_amount(self, split_amount):
    #     """Shrinks this line's amount_to_settle by split_amount and creates
    #     a new draft line for that split-off portion, linked back via
    #     parent_settlement_line_id. Both lines remain independently
    #     confirmable, each with its own fee/VAT/rate."""
    #     self.ensure_one()
    #     lc = self.lc_id

    #     if self.state != 'draft':
    #         raise ValidationError("Only a draft settlement line can be split.")

    #     if float_compare(split_amount, 0.0, precision_rounding=lc.currency_id.rounding) <= 0:
    #         raise ValidationError("The amount to split off must be greater than zero.")

    #     if float_compare(split_amount, self.amount_to_settle, precision_rounding=lc.currency_id.rounding) >= 0:
    #         raise ValidationError(
    #             "The amount to split off must be less than this line's current amount - "
    #             "otherwise there is nothing left to split."
    #         )

    #     remaining_amount = self.amount_to_settle - split_amount

    #     new_line = self.env['lc.settlement.line'].create({
    #         'lc_id': lc.id,
    #         'purchase_order_id': self.purchase_order_id.id,
    #         'shipment_id': self.shipment_id.id,
    #         'vendor_bill_id': self.vendor_bill_id.id,
    #         'parent_settlement_line_id': self.id,
    #         'amount_to_settle': split_amount,
    #         'settlement_rate': self.settlement_rate,
    #         'settlement_date': fields.Date.today(),
    #         'settlement_fee_account_id': self.settlement_fee_account_id.id,
    #         'settlement_vat_account_id': self.settlement_vat_account_id.id,
    #         'state': 'draft',
    #     })

    #     self.amount_to_settle = remaining_amount

    #     return new_line

    def _split_off_amount(self, split_amount):
        """Splits this line's current amount into two new tranches.

        If this is the ROOT line (the anchor record for the PO), the root's
        entire amount is handed off to two brand-new child records - the
        split-off piece and the remainder - and the root itself is zeroed
        out permanently. This keeps the root as a pure anchor/summary record
        that never itself represents a payable tranche, so it never shows up
        in the breakdown table and never gets opened "as if" it were a real
        tranche.

        If this is already a non-root tranche, splitting shrinks it in place
        and creates one new child for the split-off piece, same as before.
        """
        self.ensure_one()
        lc = self.lc_id

        if self.state != 'draft':
            raise ValidationError("Only a draft settlement line can be split.")

        if float_compare(split_amount, 0.0, precision_rounding=lc.currency_id.rounding) <= 0:
            raise ValidationError("The amount to split off must be greater than zero.")

        if float_compare(split_amount, self.amount_to_settle, precision_rounding=lc.currency_id.rounding) >= 0:
            raise ValidationError(
                "The amount to split off must be less than this line's current amount - "
                "otherwise there is nothing left to split."
            )

        remaining_amount = self.amount_to_settle - split_amount

        common_vals = {
            'lc_id': lc.id,
            'purchase_order_id': self.purchase_order_id.id,
            'shipment_id': self.shipment_id.id,
            'vendor_bill_id': self.vendor_bill_id.id,
            'parent_settlement_line_id': self.id,
            'settlement_rate': self.settlement_rate,
            'settlement_date': fields.Date.today(),
            'settlement_fee_account_id': self.settlement_fee_account_id.id,
            'settlement_vat_account_id': self.settlement_vat_account_id.id,
            'state': 'draft',
        }

        if self.is_root_line:
            split_line = self.env['lc.settlement.line'].create({
                **common_vals,
                'amount_to_settle': split_amount,
            })
            self.env['lc.settlement.line'].create({
                **common_vals,
                'amount_to_settle': remaining_amount,
            })
            # Root becomes a permanent zero-balance anchor - every dollar now
            # lives on one of the two new child records above.
            self.amount_to_settle = 0.0
            return split_line

        new_line = self.env['lc.settlement.line'].create({
            **common_vals,
            'amount_to_settle': split_amount,
        })
        self.amount_to_settle = remaining_amount
        return new_line
    def action_open_self(self):
        """Opens this exact tranche as a normal, fully editable page.

        Clicking a row directly on all_tranche_ids (a Many2many field) opens
        Odoo's default read-only relation-preview dialog instead of a real
        editable form - this bypasses that by navigating via a genuine
        act_window instead.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.purchase_order_id.name or 'Settlement Tranche',
            'res_model': 'lc.settlement.line',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }