from odoo import models, fields, api
from datetime import date
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero


class LCManagement(models.Model):
    _name = 'lc.management'
    _description = 'Letter of Credit'

    name = fields.Char(string="LC Reference", required=True)

    bank_journal_id = fields.Many2one(
        'account.journal',
        string="Bank Journal",
        domain="[('type', '=', 'bank')]",
        required=True
    )

    # =========================================================
    # OPENING CHARGES (ONE FEE/VAT FOR THE WHOLE LC - UNCHANGED)
    # =========================================================
    opening_fee = fields.Monetary(
        string="Opening Bank Fee",
        currency_field='company_currency_id',
        required=True
    )
    opening_fee_account_id = fields.Many2one(
        'account.account',
        string="Opening Fee Account",
        required=True
    )
    opening_date = fields.Date(
        string="Opening Date",
        required=True,
        default=fields.Date.today
    )
    opening_vat_amount = fields.Monetary(
        string="Opening VAT Amount",
        currency_field='company_currency_id',
        required=True
    )
    opening_vat_account_id = fields.Many2one(
        'account.account',
        string="Opening VAT Account",
        required=True
    )

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
        'lc.margin', string="LC margin", required=True
    )
    margin_account_id = fields.Many2one(
        'account.account', string="Margin Account", required=True
    )
    partner_id = fields.Many2one('res.partner', string="Supplier", required=True)
    release_move_id = fields.Many2one(
        'account.move',
        string='Release Journal Entry',
        readonly=True,
        help="Deprecated single-release field, kept for backward compatibility with old records. "
             "New releases are tracked per settlement line."
    )

    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
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
    can_close = fields.Boolean(
        compute="_compute_can_close",
        store=False
    )

    expiry_date = fields.Date(required=True)

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
        ('open', 'Open'),
        ('utilized', 'Utilized'),
        ('settled', 'Settled'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], default='draft')

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

    def action_open_with_confirmation(self):
        """Validates the LC, builds a plain-text preview of the journal
        entry lines that action_open will post, and opens a confirmation
        wizard. The actual posting only happens if the user confirms."""
        self.ensure_one()
        rec = self

        if rec.state != 'draft':
            raise ValidationError("Only draft LC can be opened.")
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

    def action_open(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError("Only draft LC can be opened.")

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

    def action_close(self):
        for rec in self:
            if not rec.can_close:
                raise ValidationError(
                    "LC cannot be closed yet. Ensure full utilization, all settlement "
                    "lines are confirmed, all bills are posted and paid, and the LC is fully settled."
                )

            rec.write({'state': 'closed'})

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

            if rec.state in ('draft', 'settled', 'closed'):
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

    @api.depends('settlement_line_ids.state')
    def _compute_has_draft_settlement_lines(self):
        for rec in self:
            rec.has_draft_settlement_lines = bool(
                rec.settlement_line_ids.filtered(lambda l: l.state == 'draft')
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

    # ====================== CAN CLOSE ======================
    @api.depends(
        'state',
        'remaining_amount',
        'vendor_bill_ids.state',
        'vendor_bill_ids.payment_state',
        'settlement_line_ids.state',
    )
    def _compute_can_close(self):
        for rec in self:
            no_draft_lines = not rec.settlement_line_ids.filtered(lambda l: l.state == 'draft')
            rec.can_close = (
                rec.state == 'settled'
                and no_draft_lines
                and float_is_zero(rec.remaining_amount, precision_rounding=rec.currency_id.rounding)
                and bool(rec.vendor_bill_ids)
                and all(
                    bill.payment_state == 'paid'
                    for bill in rec.vendor_bill_ids
                    if bill.state == 'posted'
                )
            )

    # =========================================================
    # SETTLEMENT STATE PROGRESSION
    # Called explicitly after a settlement line is confirmed
    # (see lc.settlement.line.action_confirm). Not a compute,
    # since state is manually-driven and a recursive compute write
    # would fight with action_open/action_close.
    # =========================================================
    def _refresh_settlement_state(self):
        for rec in self:
            if rec.state not in ('open', 'utilized'):
                continue
            no_draft_lines = not rec.settlement_line_ids.filtered(lambda l: l.state == 'draft')
            fully_paid = float_is_zero(rec.remaining_amount, precision_rounding=rec.currency_id.rounding)
            has_confirmed_line = bool(rec.settlement_line_ids.filtered(lambda l: l.state == 'confirmed'))

            if fully_paid and no_draft_lines and has_confirmed_line:
                rec.state = 'settled'


    def action_cancel_lc(self):
        for rec in self:
            if rec.state == 'cancelled':
                raise ValidationError("This LC is already cancelled.")
            if rec.state == 'closed':
                raise ValidationError("Closed LC cannot be cancelled.")

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
            if rec.state == 'closed':
                raise ValidationError("Closed LC cannot be cancelled.")

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

        if lc.state == 'closed':
            return False

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
