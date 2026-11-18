from odoo import models, fields, api
from datetime import date
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero


class LCManagement(models.Model):
    _name = 'lc.management'
    _description = 'Letter of Credit'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="LC Reference", required=True)

    bank_journal_id = fields.Many2one(
        'account.journal',
        string="Bank",
        domain="[('type', '=', 'bank')]",
        required=False
    )

    # =========================================================
    # OPENING CHARGES (ONE FEE/VAT FOR THE WHOLE LC - UNCHANGED)
    # =========================================================
    opening_fee = fields.Monetary(
        string="Bank Fee",
        currency_field='company_currency_id',
        required=False
    )
    # opening_fee_account_id = fields.Many2one(
    #     'account.account',
    #     string="Opening Fee Account",
    #     required=False
    # )
    opening_fee_account_id = fields.Many2one(
        'account.account',
        string="Fee Account",
        help="Selected per LC based on its own reference. If this account "
             "doesn't exist yet, use the 'Request Account Setup' button to "
             "notify the accountant."
    )
    
    opening_date = fields.Date(
        string="Opening Date",
        required=False,
        default=fields.Date.today
    )
    opening_vat_amount = fields.Monetary(
        string="Opening VAT Amount",
        currency_field='company_currency_id',
        required=False
    )
    # opening_vat_account_id = fields.Many2one(
    #     'account.account',
    #     string="Opening VAT Account",
    #     required=False
    # )
    opening_vat_account_id = fields.Many2one(
        'account.account',
        string="Opening VAT Account",
        default=lambda self: self.env.company.lc_default_vat_account_id,
        help="Defaults from the LC Management settings (Settings > LC Management), "
             "instead of being searched for by a hardcoded account name. Can still be "
             "changed per LC."
    )

    account_setup_request_ids = fields.One2many(
        'lc.account.setup.request', 'lc_id', string="Account Setup Requests"
    )
    pending_account_setup_count = fields.Integer(
        string="Pending Account Requests",
        compute='_compute_pending_account_setup_count'
    )

    @api.depends('account_setup_request_ids.state')
    def _compute_pending_account_setup_count(self):
        for rec in self:
            rec.pending_account_setup_count = len(
                rec.account_setup_request_ids.filtered(lambda r: r.state != 'completed')
            )

    can_edit_lc_details = fields.Boolean(
        string="Can Edit LC Details",
        compute='_compute_can_edit_lc_details',
        help="Governs the general LC fields (reference, supplier, margin "
             "type, dates, journal, currency, amount, opening charges):\n"
             "- Draft: editable (normally the Purchase Officer filling in "
             "the request).\n"
             "- Pending Approval: editable ONLY for the specific accountant "
             "this LC's opening was sent to (opening_assigned_accountant_id) "
             "- the Purchase Officer is fully locked out once submitted, "
             "she only comes back for Settlement afterwards.\n"
             "- Open/Utilized/Settled/Cancelled: locked for everyone."
    )
    can_edit_lc_accounts = fields.Boolean(
        string="Can Edit LC Accounts",
        compute='_compute_can_edit_lc_details',
        help="Governs specifically the Margin/Fee/VAT Account fields. "
             "These are auto-filled by reference matching (see "
             "_autolink_fee_account / account_account.py), so the Purchase "
             "Officer never needs or gets access to them - not even in "
             "Draft. Only the specific accountant this LC was sent to can "
             "edit them, and only while it's Pending Approval."
    )

    def _is_assigned_accountant_or_admin(self):
        self.ensure_one()
        user = self.env.user
        if user.has_group('base.group_system'):
            return True
        return bool(self.opening_assigned_accountant_id) and user.id == self.opening_assigned_accountant_id.id

    @api.depends('state', 'opening_assigned_accountant_id')
    def _compute_can_edit_lc_details(self):
        for rec in self:
            is_assigned = rec._is_assigned_accountant_or_admin()
            if rec.state == 'draft':
                rec.can_edit_lc_details = True
            elif rec.state == 'pending_approval':
                rec.can_edit_lc_details = is_assigned
            else:
                rec.can_edit_lc_details = False
            # Accounts are stricter than the general fields: never editable
            # in draft for anyone, only for the assigned accountant while
            # pending approval.
            rec.can_edit_lc_accounts = rec.state == 'pending_approval' and is_assigned

    settlement_line_count = fields.Integer(
        string="Settlement Count",
        compute='_compute_settlement_line_count'
    )

    @api.depends('settlement_line_ids.is_root_line')
    def _compute_settlement_line_count(self):
        for rec in self:
            rec.settlement_line_count = len(
                rec.settlement_line_ids.filtered(lambda l: l.is_root_line)
            )

    def action_view_settlements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f"Settlements - {self.name}",
            'res_model': 'lc.settlement.line',
            'view_mode': 'list,form',
            'domain': [('lc_id', '=', self.id), ('is_root_line', '=', True)],
            'context': {'create': False},
        }


    cancel_reason = fields.Text(readonly=True)

    # =========================================================
    # SETTLEMENT LINES (NEW - REPLACES SINGLE SETTLEMENT FIELDS)
    # =========================================================
    settlement_line_ids = fields.One2many(
        'lc.settlement.line', 'lc_id',
        string="Settlement Lines"
    )
    has_draft_settlement_lines = fields.Boolean(
        compute='_compute_has_draft_settlement_lines',
        store=False
    )

    # Core LC Fields
    lc_type_id = fields.Many2one(
        'lc.margin', string="LC margin", required=False
    )
    margin_account_id = fields.Many2one(
        'account.account', string="Margin Account", required=False,
        default=lambda self: self.env.company.lc_default_margin_account_id
    )
    partner_id = fields.Many2one('res.partner', string="Supplier", required=False)
    release_move_id = fields.Many2one(
        'account.move',
        string='Release Journal Entry',
        readonly=True,
        help="Deprecated single-release field, kept for backward compatibility with old records. "
             "New releases are tracked per settlement line."
    )

    amount = fields.Monetary(
        string='Total Amount',
        currency_field='currency_id',
        required=False
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=False,
    )
    vendor_bill_ids = fields.Many2many(
        'account.move',
        string="Vendor Bills",
        compute="_compute_vendor_bills",
        readonly=True
    )
    bill_count = fields.Integer(
        compute="_compute_vendor_bills",
        string="Number of Bills",
        readonly=True
    )

    exchange_rate = fields.Float(
        string="Exchange Rate",
        digits=(12, 6),
        default=1.0
    )
    opening_rate = fields.Float(
        string="Opening Rate",
        digits=(12, 6),
        readonly=True
    )

    # Margin
    margin_amount = fields.Monetary(
        string="LC Margin Payment",
        currency_field='currency_id',
        compute="_compute_margin_amount",
        store=True
    )
    margin_amount_company_currency = fields.Float(
        string="Margin Amount (ETB)",
        compute="_compute_margin_amount_company",
        store=True
    )

    # =========================================================
    # CUMULATIVE MARGIN RELEASE TRACKING (REPLACES margin_released BOOLEAN)
    # =========================================================
    margin_released_amount = fields.Monetary(
        string="Margin Released (Cumulative)",
        currency_field='company_currency_id',
        compute='_compute_margin_released_amount',
        store=True,
        help="Cumulative amount of margin released across all confirmed settlement lines. "
             "Derived directly from settlement lines so it can never drift out of sync."
    )
    margin_remaining_to_release = fields.Monetary(
        string="Margin Remaining to Release",
        currency_field='company_currency_id',
        compute='_compute_margin_remaining_to_release',
        store=False
    )

    settlement_rate = fields.Float(
        string="Last Settlement Rate",
        digits=(12, 6),
        readonly=True,
        help="Convenience field showing the most recent confirmed settlement line's rate."
    )

    # FX Gain/Loss - summed across confirmed settlement lines, display-only
    # (no separate posting to dedicated FX accounts).
    fx_gain_loss = fields.Monetary(
        string="FX Gain/Loss",
        currency_field='company_currency_id',
        compute="_compute_fx_gain_loss",
        store=True
    )

    rate_locked = fields.Boolean(string="Rate Locked", default=False)

    local_currency_amount = fields.Monetary(
        string="LC Opening ETB Amount",
        currency_field='company_currency_id',
        compute="_compute_local_amount",
        store=True
    )

    company_currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id.id,
        readonly=True
    )
    

    expiry_date = fields.Date(required=False)

    remaining_amount = fields.Monetary(
        string="Remaining Amount",
        currency_field='currency_id',
        compute="_compute_remaining_amount",
        store=True
    )
    paid_amount = fields.Monetary(
        string="Paid Amount",
        currency_field='currency_id',
        compute='_compute_paid_amount',
        store=True,
    )

    # Accounting
    opening_move_id = fields.Many2one(
        'account.move', string='Opening Entry', readonly=True
    )
    settlement_move_id = fields.Many2one(
        'account.move',
        string='Settlement Entry',
        readonly=True,
        help="Deprecated single-settlement field, kept for backward compatibility with old records."
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('open', 'Open'),
        ('utilized', 'Utilized'),
        ('settled', 'Settled'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)

    # =========================================================
    # OPENING REQUEST -> APPROVAL WORKFLOW
    # =========================================================
    opening_assigned_accountant_id = fields.Many2one(
        'res.users', string="Opening Sent To", readonly=True,
        help="The accountant asked to review and approve opening this LC."
    )
    opening_request_note = fields.Text(string="Note Sent With Request", readonly=True)
    opening_requested_by_id = fields.Many2one(
        'res.users', string="Opening Requested By", readonly=True
    )
    opening_request_date = fields.Datetime(string="Opening Requested On", readonly=True)
    opening_approved_by_id = fields.Many2one(
        'res.users', string="Opening Approved By", readonly=True
    )
    opening_approved_date = fields.Datetime(string="Opening Approved On", readonly=True)

    purchase_ids = fields.One2many('purchase.order', 'lc_id')

    billed_amount = fields.Monetary(
        string="Billed Amount",
        currency_field='currency_id',
        compute="_compute_billed_amount",
        store=True
    )

    used_amount = fields.Monetary(
        string="Used Amount",
        currency_field='currency_id',
        compute="_compute_used_amount",
        store=True
    )

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'LC Reference must be unique!')
    ]

    # ========================= BUTTONS =========================

    def _is_lc_accountant(self):
        return (
            self.env.user.has_group('lc_management.group_lc_accountant')
            or self.env.user.has_group('account.group_account_manager')
        )

    def _check_ready_to_request_opening(self):
        self.ensure_one()
        rec = self
        if rec.state != 'draft':
            raise ValidationError("Only draft LC can be submitted for opening.")
        if not rec.margin_account_id:
            raise ValidationError("Select Margin Account.")
        if not rec.bank_journal_id:
            raise ValidationError("Select Bank Journal.")
        if not rec.opening_fee_account_id:
            raise ValidationError(
                "Select the Opening Fee Account. If it doesn't exist yet, use "
                "'Request Account Setup' first to notify the accountant."
            )
        if not rec.opening_vat_account_id:
            raise ValidationError(
                "Select the Opening VAT Account. If it doesn't exist yet, use "
                "'Request Account Setup' first to notify the accountant."
            )
        if not rec.bank_journal_id.default_account_id:
            raise ValidationError("Bank journal missing default account.")

    def action_withdraw_opening_request(self):
        """Lets the requester pull a pending_approval LC back to draft,
        e.g. to fix something before the accountant reviews it."""
        for rec in self:
            if rec.state != 'pending_approval':
                raise ValidationError("Only an LC pending approval can be withdrawn.")
            rec.write({'state': 'draft'})
            rec.message_post(body=f"Opening request withdrawn by {self.env.user.name}.")

    def action_request_opening(self):
        """Purchase Officer step: validate the LC is ready to open, then let
        them pick which accountant should review and approve it."""
        self.ensure_one()
        self._check_ready_to_request_opening()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Opening Request',
            'res_model': 'lc.open.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lc_id': self.id},
        }

    def _send_opening_request(self, accountant, note=None):
        self.ensure_one()
        self.write({
            'state': 'pending_approval',
            'opening_assigned_accountant_id': accountant.id if accountant else False,
            'opening_request_note': note,
            'opening_requested_by_id': self.env.user.id,
            'opening_request_date': fields.Datetime.now(),
        })
        partner_ids = accountant.partner_id.ids if accountant else []
        if partner_ids:
            self.message_subscribe(partner_ids=partner_ids)
        self.message_post(
            body=(
                f"LC Opening requested by <b>{self.env.user.name}</b> for "
                f"<b>{self.name}</b>. Awaiting accountant approval."
            ),
            partner_ids=partner_ids,
        )
        if accountant:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=f"Approve LC Opening - {self.name}",
                note=note or "A purchase officer requested this LC be opened. Please review and approve.",
                user_id=accountant.id,
            )

        # Live pop-up toast (fades on its own) for whoever is online right
        # now, on top of the durable Activity/Inbox notification above -
        # that one persists and shows on the bell/activities icon even if
        # the accountant isn't logged in at this exact moment.
        if accountant:
            self.env['bus.bus']._sendone(accountant.partner_id, 'simple_notification', {
                'type': 'info',
                'title': 'LC Opening Request',
                'message': f"{self.env.user.name} asked you to review and open {self.name}.",
                'sticky': True,
                'className': 'o_lc_request_notification',
            })
        self.env.user._bus_send('simple_notification', {
            'type': 'success',
            'title': 'Request Sent',
            'message': (
                f"Opening request for {self.name} sent to {accountant.name}."
                if accountant else
                f"Opening request for {self.name} sent, but no accountant was selected."
            ),
        })

    def action_open_with_confirmation(self):
        """Accountant step: builds a plain-text preview of the journal
        entry lines that action_open will post, and opens a confirmation
        wizard. The actual posting only happens if the accountant confirms."""
        self.ensure_one()
        rec = self

        if not rec._is_lc_accountant():
            raise ValidationError("Only an Accountant can approve and open this LC.")
        if rec.state != 'pending_approval':
            raise ValidationError(
                "This LC must be submitted for opening approval first "
                "(use 'Request LC Opening')."
            )
        if not rec.margin_account_id:
            raise ValidationError("Select Margin Account.")
        if not rec.bank_journal_id:
            raise ValidationError("Select Bank Journal.")
        if not rec.opening_fee_account_id:
            raise ValidationError("Select Opening Fee Account.")
        if not rec.opening_vat_account_id:
            raise ValidationError("Select Opening VAT Account.")

        bank_account = rec.bank_journal_id.default_account_id
        if not bank_account:
            raise ValidationError("Bank journal missing default account.")

        total_credit = (
            rec.margin_amount_company_currency
            + rec.opening_fee
            + rec.opening_vat_amount
        )

        preview_lines = [
            f"Debit  {rec.margin_account_id.name}: {rec.margin_amount_company_currency:,.2f} {rec.company_currency_id.name}",
            f"Debit  {rec.opening_fee_account_id.name}: {rec.opening_fee:,.2f} {rec.company_currency_id.name}",
            f"Debit  {rec.opening_vat_account_id.name}: {rec.opening_vat_amount:,.2f} {rec.company_currency_id.name}",
            f"Credit {bank_account.name}: {total_credit:,.2f} {rec.company_currency_id.name}",
        ]
        preview_text = "\n".join(preview_lines)

        wizard = self.env['lc.open.confirm.wizard'].create({
            'lc_id': rec.id,
            'preview_text': preview_text,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirm Opening LC',
            'res_model': 'lc.open.confirm.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lc_id': rec.id},
            'res_id': wizard.id,
        }

    def _validate_before_open(self):

        # ===================================
        # REQUIRED FIELDS
        # ===================================

        required_fields = [
            ("name", "LC Reference"),
            ("bank_journal_id", "Bank Journal"),
            ("partner_id", "Beneficiary"),
            ("currency_id", "Currency"),
            ("amount", "LC Amount"),
            ("opening_date", "Opening Date"),
            ("expiry_date", "Expiry Date"),
            ("exchange_rate", "Exchange Rate"),
            ("lc_type_id", "LC Margin"),
            ("margin_account_id", "Margin Account"),
            ("opening_fee", "Opening Fee"),
            ("opening_fee_account_id", "Opening Fee Account"),
            ("opening_vat_account_id", "Opening VAT Account"),
        ]

        for rec in self:

            missing = []

            # ===================================
            # CHECK REQUIRED FIELDS
            # ===================================

            for field_name, label in required_fields:

                value = rec[field_name]

                if value in (False, None, ''):
                    missing.append(label)

            if missing:
                raise ValidationError(
                    "Please complete the following fields before opening the LC:\n\n- "
                    + "\n- ".join(missing)
                )

            # ===================================
            # BUSINESS VALIDATIONS
            # ===================================

            if rec.amount <= 0:
                raise ValidationError(
                    "LC Amount must be greater than zero."
                )

            if rec.exchange_rate <= 0:
                raise ValidationError(
                    "Exchange Rate must be greater than zero."
                )

            if rec.lc_type_id.margin_percentage < 0:
                raise ValidationError(
                    "Margin Percentage cannot be negative."
                )

            if rec.lc_type_id.margin_percentage > 100:
                raise ValidationError(
                    "Margin Percentage cannot exceed 100%."
                )

            if rec.margin_amount_company_currency <= 0:
                raise ValidationError(
                    "Margin Amount must be greater than zero - check the LC "
                    "Amount and LC Margin percentage."
                )

            if rec.opening_fee <= 0:
                raise ValidationError(
                    "Opening Fee must be greater than zero."
                )

            if rec.opening_vat_amount <= 0:
                raise ValidationError(
                    "Opening VAT Amount must be greater than zero."
                )

            if rec.expiry_date <= rec.opening_date:
                raise ValidationError(
                    "Expiry Date must be later than Opening Date."
                )

            # ===================================
            # ACCOUNTING VALIDATIONS
            # ===================================

            if rec.bank_journal_id.default_account_id is False:
                raise ValidationError(
                    "The selected Bank Journal does not have a Default Account configured."
                )

            if rec.margin_account_id == rec.opening_fee_account_id:
                raise ValidationError(
                    "Margin Account and Opening Fee Account cannot be the same."
                )

            if rec.margin_account_id == rec.opening_vat_account_id:
                raise ValidationError(
                    "Margin Account and Opening VAT Account cannot be the same."
                )

            if rec.opening_fee_account_id == rec.opening_vat_account_id:
                raise ValidationError(
                    "Opening Fee Account and Opening VAT Account cannot be the same."
                )

    def action_open(self):
        self._validate_before_open()
        for rec in self:
            if rec.state != 'pending_approval':
                raise ValidationError("Only an LC pending approval can be opened.")

            if not rec.margin_account_id:
                raise ValidationError("Select Margin Account.")
            if not rec.bank_journal_id:
                raise ValidationError("Select Bank Journal.")
            if not rec.opening_fee_account_id:
                raise ValidationError("Select Opening Fee Account.")
            if not rec.opening_vat_account_id:
                raise ValidationError("Select Opening VAT Account.")

            bank_account = rec.bank_journal_id.default_account_id
            if not bank_account:
                raise ValidationError("Bank journal missing default account.")

            total_credit = (
                rec.margin_amount_company_currency
                + rec.opening_fee
                + rec.opening_vat_amount
            )

            # FREEZE OPENING RATE
            rec.opening_rate = rec.exchange_rate

            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': rec.bank_journal_id.id,
                'line_ids': [
                    (0, 0, {
                        'name': f"LC Margin Payment - {rec.name}",
                        'account_id': rec.margin_account_id.id,
                        'debit': rec.margin_amount_company_currency,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': f"LC Opening Fee - {rec.name}",
                        'account_id': rec.opening_fee_account_id.id,
                        'debit': rec.opening_fee,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': f"LC Opening VAT - {rec.name}",
                        'account_id': rec.opening_vat_account_id.id,
                        'debit': rec.opening_vat_amount,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': f"LC Open - {rec.name}",
                        'account_id': bank_account.id,
                        'debit': 0.0,
                        'credit': total_credit,
                    }),
                ]
            })

            move.action_post()
            rec.rate_locked = True

            rec.write({
                'state': 'open',
                'opening_move_id': move.id,
            })

   

    # -------------------------
    # USAGE CALCULATION
    # -------------------------
    @api.depends('purchase_ids.amount_total', 'purchase_ids.state', 'purchase_ids.currency_id')
    def _compute_used_amount(self):
        for rec in self:
            total_used = 0.0
            for po in rec.purchase_ids:
                if po.state not in ('purchase', 'done'):
                    continue
                if po.currency_id == rec.currency_id:
                    total_used += po.amount_total
                else:
                    total_used += po.currency_id._convert(
                        po.amount_total,
                        rec.currency_id,
                        rec.env.company,
                        fields.Date.context_today(self)
                    )
            rec.used_amount = total_used

            if rec.state in ('draft', 'settled'):
                continue

            if float_is_zero(total_used, precision_rounding=rec.currency_id.rounding):
                rec.state = 'open'
            else:
                rec.state = 'utilized'

    # -------------------------
    # EXPIRY VALIDATION
    # -------------------------
    @api.constrains('expiry_date')
    def _check_expiry(self):
        for rec in self:
            if rec.expiry_date and rec.expiry_date < date.today():
                raise ValidationError("LC is expired!")

    # -------------------------
    # MARGIN CALCULATION
    # -------------------------
    @api.depends('amount', 'lc_type_id.margin_percentage')
    def _compute_margin_amount(self):
        for rec in self:
            rec.margin_amount = (rec.amount * rec.lc_type_id.margin_percentage) / 100

    @api.depends('margin_amount_company_currency', 'margin_released_amount')
    def _compute_margin_remaining_to_release(self):
        for rec in self:
            rec.margin_remaining_to_release = max(
                rec.margin_amount_company_currency - rec.margin_released_amount, 0.0
            )

    @api.depends('settlement_line_ids.margin_released_this_line', 'settlement_line_ids.state')
    def _compute_margin_released_amount(self):
        for rec in self:
            confirmed_lines = rec.settlement_line_ids.filtered(lambda l: l.state == 'confirmed')
            rec.margin_released_amount = sum(confirmed_lines.mapped('margin_released_this_line'))

    @api.onchange('currency_id')
    def _onchange_currency_id(self):
        if self.rate_locked:
            return
        company_currency = self.env.company.currency_id

        if self.currency_id and self.currency_id != company_currency:
            rate = self.env['res.currency']._get_conversion_rate(
                self.currency_id,
                company_currency,
                self.env.company,
                fields.Date.today()
            )
            self.exchange_rate = rate
        else:
            self.exchange_rate = 1.0

    @api.depends('amount', 'exchange_rate')
    def _compute_local_amount(self):
        for rec in self:
            rec.local_currency_amount = rec.amount * rec.exchange_rate

    # =========================================================
    # FX GAIN/LOSS - SUMMED ACROSS CONFIRMED SETTLEMENT LINES
    # =========================================================
    @api.depends('settlement_line_ids.fx_gain_loss_this_line', 'settlement_line_ids.state')
    def _compute_fx_gain_loss(self):
        for rec in self:
            confirmed_lines = rec.settlement_line_ids.filtered(lambda l: l.state == 'confirmed')
            rec.fx_gain_loss = sum(confirmed_lines.mapped('fx_gain_loss_this_line'))

    @api.depends('margin_amount', 'exchange_rate')
    def _compute_margin_amount_company(self):
        for rec in self:
            rec.margin_amount_company_currency = rec.margin_amount * rec.exchange_rate

    @api.depends('settlement_line_ids.state', 'settlement_line_ids.amount_to_settle')
    def _compute_has_draft_settlement_lines(self):
        for rec in self:
            rec.has_draft_settlement_lines = bool(
                rec.settlement_line_ids.filtered(
                    lambda l: l.state == 'draft'
                    and not float_is_zero(l.amount_to_settle, precision_rounding=rec.currency_id.rounding)
                )
            )
    # ====================== BILLED AMOUNT ======================
    @api.depends('purchase_ids.invoice_ids',
                 'purchase_ids.invoice_ids.state',
                 'purchase_ids.invoice_ids.amount_total',
                 'purchase_ids.invoice_ids.currency_id')
    def _compute_billed_amount(self):
        for rec in self:
            total_billed = 0.0
            for po in rec.purchase_ids:
                for bill in po.invoice_ids:
                    if bill.state == 'posted':
                        if bill.currency_id == rec.currency_id:
                            total_billed += bill.amount_total
                        else:
                            total_billed += bill.currency_id._convert(
                                bill.amount_total,
                                rec.currency_id,
                                rec.env.company,
                                fields.Date.context_today(self)
                            )
            rec.billed_amount = total_billed

    # ====================== REMAINING AMOUNT ======================
    @api.depends('amount', 'paid_amount')
    def _compute_remaining_amount(self):
        for rec in self:
            rec.remaining_amount = rec.amount - rec.paid_amount

    # ====================== VENDOR BILLS ======================
    @api.depends('purchase_ids.invoice_ids')
    def _compute_vendor_bills(self):
        for rec in self:
            bills = self.env['account.move']
            for po in rec.purchase_ids:
                bills |= po.invoice_ids
            rec.vendor_bill_ids = bills
            rec.bill_count = len(bills)

    @api.depends(
    'purchase_ids.invoice_ids.amount_total',
    'purchase_ids.invoice_ids.amount_residual',
    'purchase_ids.invoice_ids.state',
    'purchase_ids.invoice_ids.currency_id'
    )
    def _compute_paid_amount(self):
        for rec in self:
            total_paid = 0.0
            for po in rec.purchase_ids:
                for bill in po.invoice_ids.filtered(lambda b: b.state == 'posted'):
                    paid = bill.amount_total - bill.amount_residual
                    if bill.currency_id == rec.currency_id:
                        total_paid += paid
                    else:
                        total_paid += bill.currency_id._convert(
                            paid,
                            rec.currency_id,
                            rec.env.company,
                            fields.Date.context_today(rec)
                        )
            rec.paid_amount = total_paid

        
        self._compute_remaining_amount()
        self._refresh_settlement_state()
    @api.model
    def _cron_refresh_settlement_states(self):
        """Scheduled fallback: periodically re-checks every Utilized LC in
        case a vendor bill payment reconciled since the last check. Doing
        this here, as an explicit scheduled action, avoids the unreliable
        pattern of writing lc.state as a side effect inside a computed field.
        """
        lcs = self.search([('state', '=', 'utilized')])
        for lc in lcs:
            lc._compute_paid_amount()
            lc._compute_remaining_amount()
            lc._refresh_settlement_state()
    
    @api.depends(
        'state',
        'remaining_amount',
        'vendor_bill_ids.state',
        'vendor_bill_ids.payment_state',
        'settlement_line_ids.state',
    )
   
    def _refresh_settlement_state(self):
        for rec in self:
            if rec.state not in ('open', 'utilized'):
                continue
            no_draft_lines = not rec.settlement_line_ids.filtered(
                lambda l: l.state == 'draft'
                and not float_is_zero(l.amount_to_settle, precision_rounding=rec.currency_id.rounding)
            )
            fully_paid = float_is_zero(rec.remaining_amount, precision_rounding=rec.currency_id.rounding)
            has_confirmed_line = bool(rec.settlement_line_ids.filtered(lambda l: l.state == 'confirmed'))

            if fully_paid and no_draft_lines and has_confirmed_line:
                rec.state = 'settled'

    def action_cancel_lc(self):
        for rec in self:
            if rec.state == 'cancelled':
                raise ValidationError("This LC is already cancelled.")

            active_pos = rec.purchase_ids.filtered(lambda po: po.state != 'cancel')
            if active_pos:
                po_names = ", ".join(active_pos.mapped('name'))
                raise ValidationError(
                    f"This LC cannot be cancelled because the following Purchase Orders are still active:\n\n"
                    f"{po_names}\n\nCancel them first and try again."
                )

            posted_bills = rec.vendor_bill_ids.filtered(lambda b: b.state == 'posted')
            if posted_bills:
                raise ValidationError(
                    "This LC cannot be cancelled because posted Vendor Bills already exist.\n\n"
                    "Reverse the Vendor Bills first."
                )

            if rec.state == 'settled':
                if not self.env.user.has_group('account.group_account_manager'):
                    raise ValidationError("Only Accounting Managers can cancel a settled LC.")

            # Reverse all confirmed settlement lines (fee/VAT + margin release moves)
            for line in rec.settlement_line_ids.filtered(lambda l: l.state == 'confirmed'):
                line.action_cancel_line()

            # Reverse legacy single-move fields if present (old records)
            if rec.settlement_move_id:
                rec._reverse_move(rec.settlement_move_id)
            if rec.release_move_id:
                rec._reverse_move(rec.release_move_id)

            # Reverse opening entry
            if rec.opening_move_id:
                rec._reverse_move(rec.opening_move_id)

            rec.write({
                'state': 'cancelled',
                'rate_locked': False,
            })

    def _reverse_move(self, move):
        """Reverse and post an accounting move."""
        if not move:
            return
        reverse_move = move._reverse_moves(
            default_values_list=[{
                'date': fields.Date.today(),
                'ref': f"Reversal of {move.name}",
            }],
            cancel=False,
        )
        reverse_move.action_post()

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(
                    "Only Draft LC records can be deleted.\n\nUse Cancel LC instead."
                )
        return super().unlink()

    def _validate_lc_cancellation(self):
        for rec in self:
            if rec.state == 'cancelled':
                raise ValidationError("This LC is already cancelled.")

            active_pos = rec.purchase_ids.filtered(lambda po: po.state != 'cancel')
            if active_pos:
                po_names = ", ".join(active_pos.mapped('name'))
                raise ValidationError(
                    f"This LC cannot be cancelled because the following Purchase Orders are still active:\n\n"
                    f"{po_names}\n\nCancel them first and try again."
                )

            posted_bills = rec.vendor_bill_ids.filtered(lambda b: b.state == 'posted')
            if posted_bills:
                raise ValidationError(
                    "This LC cannot be cancelled because posted Vendor Bills exist.\n\n"
                    "Reverse the Vendor Bills first."
                )

            if rec.state == 'settled':
                if not self.env.user.has_group('account.group_account_manager'):
                    raise ValidationError("Only Accounting Managers can cancel a settled LC.")

    # =========================================================
    # NOTIFY ACCOUNTANT: GL ACCOUNT NOT YET CREATED
    # =========================================================
    def action_request_fee_account_setup(self):
        self.ensure_one()
        return self._open_account_setup_request_form('fee')

    def action_request_vat_account_setup(self):
        self.ensure_one()
        return self._open_account_setup_request_form('vat')

    def _open_account_setup_request_form(self, purpose):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Request Account Setup',
            'res_model': 'lc.account.setup.request',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lc_id': self.id,
                'default_account_purpose': purpose,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._autolink_fee_account()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get('opening_fee_account_id'):
            for rec in self:
                self.env['lc.account.setup.request']._auto_complete_for_lc(rec, 'fee')
        if vals.get('opening_vat_account_id'):
            for rec in self:
                self.env['lc.account.setup.request']._auto_complete_for_lc(rec, 'vat')
        if vals.get('name'):
            self._autolink_fee_account()
        return res

    def _autolink_fee_account(self):
        """Auto-fill the Fee Account from the Chart of Accounts by matching
        this LC's own reference (name) - no company-wide config involved,
        since every LC's fee account is a distinct account by design.

        This covers the "account created after the LC" direction. The
        opposite direction (LC created after the account already exists)
        is covered by account.account's own create()/write() hook calling
        back into this same matching, see models/account_account.py.
        """
        Account = self.env['account.account'].sudo()
        for rec in self:
            if rec.opening_fee_account_id or not rec.name:
                continue
            match = Account.search([('name', 'ilike', rec.name)], limit=1)
            if match:
                rec.opening_fee_account_id = match.id

    @api.onchange('name')
    def _onchange_name_autolink_fee_account(self):
        """Live UI feedback: the moment you type the LC reference and click
        away, check for a matching GL account immediately - no Save needed.
        This doesn't touch the database (onchange never does); the actual
        persisted link still happens through _autolink_fee_account() on
        create/write, same as before. This is purely so the user sees it
        fill in right away instead of only after saving."""
        if not self.opening_fee_account_id and self.name:
            match = self.env['account.account'].sudo().search([('name', 'ilike', self.name)], limit=1)
            if match:
                self.opening_fee_account_id = match

    def action_open_cancel_wizard(self):
        self.ensure_one()
        self._validate_lc_cancellation()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Cancel LC',
            'res_model': 'lc.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lc_id': self.id},
        }

    # =========================================================
    # CALLED FROM shipment_tracking.py WHEN A SHIPMENT REACHES ITS
    # FINAL DESTINATION (action_set_arrived_at_destination).
    # One settlement line per shipment/PO - created the moment goods
    # land, independent of bill/payment timing, so the PO is never
    # stuck waiting on Odoo's normal billing cycle. The amount mirrors
    # the PO's own total exactly - never manually typed - so there is
    # no way for a confirmed settlement to drift from the real PO value.
    # =========================================================
    def _create_draft_settlement_line_for_shipment(self, purchase_order, shipment):
        self.ensure_one()
        lc = self

        # Avoid duplicate draft/confirmed lines for the same PO/shipment
        existing = lc.settlement_line_ids.filtered(
            lambda l: l.purchase_order_id.id == purchase_order.id and l.state != 'cancelled'
        )
        if existing:
            return existing[0]

        amount_to_settle = purchase_order.amount_total
        if purchase_order.currency_id != lc.currency_id:
            amount_to_settle = purchase_order.currency_id._convert(
                purchase_order.amount_total,
                lc.currency_id,
                lc.env.company,
                fields.Date.context_today(lc)
            )

        company_currency = lc.env.company.currency_id
        default_rate = self.env['res.currency']._get_conversion_rate(
            lc.currency_id,
            company_currency,
            lc.env.company,
            fields.Date.today()
        )

        line = self.env['lc.settlement.line'].create({
            'lc_id': lc.id,
            'purchase_order_id': purchase_order.id,
            'shipment_id': shipment.id,
            'amount_to_settle': amount_to_settle,
            'settlement_rate': default_rate,
            'settlement_date': fields.Date.today(),
            'settlement_fee_account_id': lc.opening_fee_account_id.id,
            'settlement_vat_account_id': lc.opening_vat_account_id.id,
            'state': 'draft',
        })
        return line
    def action_recheck_settlement_status(self):
        """Manually re-runs the settled-state check. Useful for diagnosing
        whether _refresh_settlement_state is wired up correctly, and as a
        safety valve if a recompute chain ever gets missed."""
        for rec in self:
            rec._compute_paid_amount()
            rec._compute_remaining_amount()
            rec._refresh_settlement_state()