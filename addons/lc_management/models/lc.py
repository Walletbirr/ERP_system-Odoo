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

    # Opening Charges
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


    cancel_reason = fields.Text(
        readonly=True
    )


    settlement_fee = fields.Monetary(
        string="LC Settlement Fee",
        currency_field='company_currency_id',
        # required=True
    )
    settlement_fee_account_id = fields.Many2one(
        'account.account', 
        string="Settlement Fee Account",
        # required=True
    )


    settlement_vat_amount = fields.Monetary(
        string="Settlement VAT Amount",
        currency_field='company_currency_id',
        # required=True
    )
    settlement_vat_account_id = fields.Many2one(
        'account.account', 
        string="Settlement VAT Account",
        # required=True
    )
    settlement_date = fields.Date(
        string="Settlement Date",
        # required=True,
        default=fields.Date.today
    )

    # Core LC Fields
    lc_type_id = fields.Many2one(
        'lc.type', string="LC Type", required=True
    )
    margin_account_id = fields.Many2one(
        'account.account', string="Margin Account", required=True
    )
    partner_id = fields.Many2one('res.partner', string="Supplier", required=True)
    release_move_id = fields.Many2one(
    'account.move',
    string='Release Journal Entry',
    readonly=True,
    help="Journal entry created when LC margin is released upon settlement or closure."
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

    # Settlement
    settlement_currency_amount = fields.Monetary(
        string="Settlement USD Amount",
        currency_field='currency_id'
    )
    settlement_etb_amount = fields.Monetary(
        string="Settlement ETB Amount",
        currency_field='company_currency_id',
        compute="_compute_settlement_etb",
        store=True
    )
    settlement_rate = fields.Float(digits=(12, 6))

    margin_released = fields.Boolean(string="Margin Released", default=False, readonly=True)
    # FX Gain/Loss
    fx_gain_loss = fields.Monetary(
    string="FX Gain/Loss",
    currency_field='company_currency_id',
    compute="_compute_fx_gain_loss",
    store=True
    )
    fx_gain_account_id = fields.Many2one(
        'account.account', string="FX Gain Account"
    )
    fx_loss_account_id = fields.Many2one(
        'account.account', string="FX Loss Account"
    )

    rate_locked = fields.Boolean(string="Rate Locked", default=False)

    local_currency_amount = fields.Monetary(
    string="LC Opening ETB Amount ",
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
        'account.move', string='Settlement Entry', readonly=True
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

    def action_open(self):

        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(
                    "Only draft LC can be opened."
                )

            # =========================
            # REQUIRED VALIDATIONS
            # =========================
            if not rec.margin_account_id:
                raise ValidationError(
                    "Select Margin Account."
                )
            
            if not rec.bank_journal_id:
                raise ValidationError(
                    "Select Bank Journal."
                )

            if not rec.opening_fee_account_id:
                raise ValidationError(
                    "Select Opening Fee Account."
                )

            if not rec.opening_vat_account_id:
                raise ValidationError(
                    "Select Opening VAT Account."
                )
            

            bank_account = rec.bank_journal_id.default_account_id

            if not bank_account:
                raise ValidationError(
                    "Bank journal missing default account."
                )


            # =========================
            # TOTAL CREDIT AMOUNT
            # =========================
            total_credit = (
            rec.margin_amount_company_currency
            + rec.opening_fee
            + rec.opening_vat_amount
            )
        # =========================
        # FREEZE OPENING RATE
        # =========================
            rec.opening_rate = rec.exchange_rate
        # =========================
        # ACCOUNTING ENTRY
        # =========================
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': rec.bank_journal_id.id,

                'line_ids': [

               
                # ----------------------------
                # DR LC Margin/GIT
                # ----------------------------
                    (0, 0, {
                        'name': f"LC Margin Payment - {rec.name}",
                        'account_id': rec.margin_account_id.id,
                        'debit': rec.margin_amount_company_currency,
                        'credit': 0.0,
                    }),
                # ---------------------------------
                # OPENING BANK CHARGE
                # ---------------------------------

                    (0, 0, {
                        'name': f"LC Opening Fee - {rec.name}",
                        'account_id': rec.opening_fee_account_id.id,
                        'debit': rec.opening_fee,
                        'credit': 0.0,
                    }),

                # ---------------------------------
                # OPENING TAX
                # ---------------------------------

                    (0, 0, {
                        'name': f"LC Opening VAT - {rec.name}",
                        'account_id': rec.opening_vat_account_id.id,
                        'debit': rec.opening_vat_amount,
                        'credit': 0.0,
                    }),

                # ---------------------------------
                # BANK CREDIT
                # ---------------------------------

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
    def action_settle(self):
        for rec in self:
            if rec.state != 'utilized':
                raise ValidationError("Only utilized LC can be settled.")
        # =========================
        # PURCHASE RECEIPT VALIDATION
        # =========================
        
        if not rec.purchase_ids:
            raise ValidationError(
                "No Purchase Orders are linked to this LC."
            )
        for po in rec.purchase_ids:
            if po.state not in ('purchase', 'done'):
                raise ValidationError(
                    f"Purchase Order {po.name} is not confirmed."
                )
            
        for po in rec.purchase_ids:

            incoming_pickings = po.picking_ids.filtered(
                lambda p: p.picking_type_code == 'incoming'
            )

            if not incoming_pickings:
                raise ValidationError(
                    f"Purchase Order {po.name} has no receipt."
                )

            not_done = incoming_pickings.filtered(
                lambda p: p.state != 'done'
            )

            if not_done:
                raise ValidationError(
                    f"Purchase Order {po.name} still has receipts that are not validated."
                )
            # Auto fill settlement amount if empty
            if not rec.settlement_currency_amount:
                rec.settlement_currency_amount = rec.remaining_amount

            # ====================== SETTLEMENT RATE FIX ======================
            if float_is_zero(rec.settlement_rate, precision_digits=6):
                # Only fetch rate if user didn't enter any
                company_currency = self.env.company.currency_id
                settlement_rate = self.env['res.currency']._get_conversion_rate(
                    rec.currency_id,
                    company_currency,
                    self.env.company,
                    rec.settlement_date or fields.Date.today()
                )
                rec.settlement_rate = settlement_rate
            # Else: Keep the rate the user manually entered
            # =================================================================

            # ========================= VALIDATIONS =========================
            if not rec.settlement_fee:
                raise ValidationError("Please enter settlement fee.")

            if not rec.settlement_fee_account_id or not rec.settlement_vat_account_id:
                raise ValidationError("Please select settlement fee and VAT accounts.")

            if not rec.settlement_date:
                raise ValidationError("Please enter settlement date.")

            bank_account = rec.bank_journal_id.default_account_id
            if not bank_account:
                raise ValidationError("Bank journal missing default account.")
            if rec.settlement_currency_amount + rec.margin_amount > rec.amount:
                raise ValidationError(
                "Settlement amount cannot exceed LC amount."
            )

            # ========================= ACCOUNTING ENTRY =========================
            total_credit = rec.settlement_fee + rec.settlement_vat_amount

            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': rec.bank_journal_id.id,
                'line_ids': [
                    (0, 0, {
                        'name': f"LC Settlement Fee - {rec.name}",
                        'account_id': rec.settlement_fee_account_id.id,
                        'debit': rec.settlement_fee,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': f"LC Settlement VAT - {rec.name}",
                        'account_id': rec.settlement_vat_account_id.id,
                        'debit': rec.settlement_vat_amount,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': f"LC Settlement - {rec.name}",
                        'account_id': bank_account.id,
                        'debit': 0.0,
                        'credit': total_credit,
                    }),
                ]
            })

            move.action_post()

            rec.write({
                'state': 'settled',
                'settlement_move_id': move.id,
            })
    def action_close(self):
        for rec in self:
            if not rec.can_close:
                raise ValidationError("LC cannot be closed yet. Ensure full utilizationused, bills are posted, and state is Settled.")

            # Optional: Release margin (reverse or adjust the opening entry)
            if rec.opening_move_id:
                # You can create a reversing entry or specific margin release move
                pass  # Add logic here if needed

            rec.write({
                'state': 'closed',
                # Maybe store close_date = fields.Date.today()
            })
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
                    # Convert PO amount to LC currency
                    total_used += po.currency_id._convert(
                        po.amount_total,
                        rec.currency_id,
                        rec.env.company,
                        fields.Date.context_today(self)
                    )

            rec.used_amount = total_used

            # ========================
            # Auto State Update
            # ========================
            if rec.state in ('draft', 'settled', 'closed'):
                continue

            if float_is_zero(total_used, precision_rounding=rec.currency_id.    rounding):
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

    @api.depends('amount', 'lc_type_id.margin_percentage')
    def _compute_margin_amount(self):
        for rec in self:
            rec.margin_amount = (
                rec.amount * rec.lc_type_id.margin_percentage
            ) / 100
    
    @api.depends(
    'amount',
    'settlement_rate',
    'margin_amount',
    'opening_rate'
    )
    def _compute_settlement_etb(self):

        for rec in self:

            final_total_etb = (
                rec.amount
                * rec.settlement_rate
            )

            margin_paid_etb = (
                rec.margin_amount
                * rec.opening_rate
            )

            rec.settlement_etb_amount = (
                final_total_etb
                - margin_paid_etb
            )
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
            rec.local_currency_amount = (
                rec.amount * rec.exchange_rate
            )

    @api.depends(
    'settlement_currency_amount',
    'opening_rate',
    'settlement_rate',
    'margin_amount'
    )
    def _compute_fx_gain_loss(self):

        for rec in self:

            # ---------------------------------
            # NO MARGIN = NO FX GAIN/LOSS
            # ---------------------------------

            if rec.margin_amount <= 0:

                rec.fx_gain_loss = 0.0
                continue

            # ---------------------------------
            # CALCULATE FX DIFFERENCE
            # ---------------------------------

            opening_value = (
                rec.amount
                * rec.opening_rate
            )

            settlement_value = (
                rec.amount
                * rec.settlement_rate
            )

            rec.fx_gain_loss = (
                opening_value
              - settlement_value
            )

    @api.depends(
    'margin_amount',
    'exchange_rate'
    )
    def _compute_margin_amount_company(self):
        for rec in self:
            rec.margin_amount_company_currency = (
                rec.margin_amount
                * rec.exchange_rate
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
                    # Only consider posted bills
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

            # ====================== AUTO STATE UPDATE ======================
            if rec.state in ('draft', 'settled', 'closed'):
                continue

            if float_is_zero(total_billed, precision_rounding=rec.currency_id.rounding):
                rec.state = 'open'
            else:
                rec.state = 'utilized'


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
                for bill in po.invoice_ids.filtered(
                    lambda b: b.state == 'posted'
                ):
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
    'vendor_bill_ids.payment_state'
    )
    def _compute_can_close(self):
        for rec in self:
            rec.can_close = (
                rec.state == 'settled'
                and float_is_zero(
                    rec.remaining_amount, 
                    precision_rounding=rec.currency_id.rounding
                )
                and bool(rec.vendor_bill_ids)
                and all(
                        bill.payment_state == 'paid'
                        for bill in rec.vendor_bill_ids
                        if bill.state == 'posted'
                    )
            )
    def action_cancel_lc(self):

        for rec in self:

            # ===================================
            # ALREADY CANCELLED
            # ===================================

            if rec.state == 'cancelled':
                raise ValidationError(
                    "This LC is already cancelled."
                )

            # ===================================
            # CLOSED LC
            # ===================================

            if rec.state == 'closed':
                raise ValidationError(
                    "Closed LC cannot be cancelled."
                )

            # ===================================
            # PURCHASE ORDER VALIDATION
            # ===================================

            active_pos = rec.purchase_ids.filtered(
                lambda po: po.state != 'cancel'
            )

            if active_pos:
                po_names = ", ".join(active_pos.mapped('name'))

                raise ValidationError(
                    f"This LC cannot be cancelled because the following Purchase Orders are still active:\n\n"
                    f"{po_names}\n\n"
                    f"Cancel them first and try again."
                )
            # ===================================
            # VENDOR BILL VALIDATION
            # ===================================

            posted_bills = rec.vendor_bill_ids.filtered(
                lambda b: b.state == 'posted'
            )

            if posted_bills:
                raise ValidationError(
                    "This LC cannot be cancelled because "
                    "posted Vendor Bills already exist.\n\n"
                    "Reverse the Vendor Bills first."
                )

            # ===================================
            # EXTRA PROTECTION FOR SETTLED LCs
            # ===================================

            if rec.state == 'settled':

                if not self.env.user.has_group(
                    'account.group_account_manager'
                ):
                    raise ValidationError(
                        "Only Accounting Managers can cancel a settled LC."
                    )

            # ===================================
            # REVERSE SETTLEMENT ENTRY
            # ===================================

            if rec.settlement_move_id:
                rec._reverse_move(
                    rec.settlement_move_id
                )

            # ===================================
            # REVERSE RELEASE ENTRY
            # ===================================

            if rec.release_move_id:
                rec._reverse_move(
                    rec.release_move_id
                )

            # ===================================
            # REVERSE OPENING ENTRY
            # ===================================

            if rec.opening_move_id:
                rec._reverse_move(
                    rec.opening_move_id
                )

            # ===================================
            # RESET IMPORTANT FIELDS
            # ===================================

            rec.write({
                'state': 'cancelled',
                'rate_locked': False,
                'margin_released': False,
            })
    def _reverse_move(self, move):
        """
        Reverse and post an accounting move.
        """
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
                    "Only Draft LC records can be deleted.\n\n"
                    "Use Cancel LC instead."
                )

        return super().unlink()
    def _validate_lc_cancellation(self):

        for rec in self:

            if rec.state == 'cancelled':
                raise ValidationError(
                    "This LC is already cancelled."
                )

            if rec.state == 'closed':
                raise ValidationError(
                    "Closed LC cannot be cancelled."
                )

            active_pos = rec.purchase_ids.filtered(
                lambda po: po.state != 'cancel'
            )

            if active_pos:
                po_names = ", ".join(active_pos.mapped('name'))

                raise ValidationError(
                    f"This LC cannot be cancelled because the following Purchase Orders are still active:\n\n"
                    f"{po_names}\n\n"
                    f"Cancel them first and try again."
                )

            posted_bills = rec.vendor_bill_ids.filtered(
                lambda b: b.state == 'posted'
            )

            if posted_bills:
                raise ValidationError(
                    "This LC cannot be cancelled because posted Vendor Bills exist.\n\n"
                    "Reverse the Vendor Bills first."
                )

            if rec.state == 'settled':

                if not self.env.user.has_group(
                    'account.group_account_manager'
                ):
                    raise ValidationError(
                        "Only Accounting Managers can cancel a settled LC."
                    )
    def action_open_cancel_wizard(self):

        self.ensure_one()

        # Run all validations here first

        self._validate_lc_cancellation()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Cancel LC',
            'res_model': 'lc.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lc_id': self.id,
            },
        }

