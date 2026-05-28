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
        currency_field='company_currency_id'
    )
    opening_fee_account_id = fields.Many2one(
        'account.account', string="Opening Fee Account"
    )
    opening_date = fields.Date(
        string="Opening Date",
        default=fields.Date.today
    )
    opening_vat_amount = fields.Monetary(
        string="Opening VAT Amount",
        currency_field='company_currency_id'
    )
    opening_vat_account_id = fields.Many2one(
        'account.account', string="Opening VAT Account"
    )

    # # Opening Tax
    # opening_tax_id = fields.Many2one(
    #     'account.tax',
    #     string="Opening Tax Type",
    #     domain="[('type_tax_use', '=', 'purchase')]"
    # )

    # opening_tax_amount = fields.Monetary(
    #     string="Opening Tax Amount",
    #     currency_field='company_currency_id',
    #     compute="_compute_opening_tax_amount",
    #     store=True
    # )

    # opening_tax_account_id = fields.Many2one(
    #     'account.account',
    #     string="Opening Tax Account"
    # )
    # Settlement Charges
    settlement_fee = fields.Monetary(
        string="LC Settlement Fee",
        currency_field='company_currency_id'
    )
    settlement_fee_account_id = fields.Many2one(
        'account.account', string="Settlement Fee Account"
    )


    # # Settlement Tax
    # settlement_tax_id = fields.Many2one(
    #     'account.tax',
    #     string="Settlement Tax Type",
    #     domain="[('type_tax_use', '=', 'purchase')]"
    # )

    # settlement_tax_amount = fields.Monetary(
    #     string="Settlement Tax Amount",
    #     currency_field='company_currency_id',
    #     compute="_compute_settlement_tax_amount",
    # store=True
    # )

    # settlement_tax_account_id = fields.Many2one(
    #     'account.account',
    #     string="Settlement Tax Account"
    # )


    settlement_vat_amount = fields.Monetary(
        string="Settlement VAT Amount",
        currency_field='company_currency_id'
    )
    settlement_vat_account_id = fields.Many2one(
        'account.account', string="Settlement VAT Account"
    )
    settlement_date = fields.Date(
        string="Settlement Date",
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

    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
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

            # total_credit = (
            #     rec.amount
            #     + rec.opening_fee
            #     + rec.opening_tax_amount
            # )
            # total_credit = (
            #     rec.margin_amount
            #     + rec.opening_fee
            #     + rec.opening_tax_amount
            # )
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

                # ---------------------------------
                # LC MARGIN FREEZE
                # ---------------------------------

                    # (0, 0, {
                    #     'name': f"LC Margin - {rec.name}",
                    #     'account_id': rec.margin_account_id.id,
                    #     'debit': rec.margin_amount_company_currency,
                    #     'credit': 0.0,
                    # }),
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

    # def action_settle(self):

    #     for rec in self:
    #         if rec.state != 'utilized':
    #             raise ValidationError(
    #                 "Only utilized LC can be settled."
    #         )

    #         if not rec.settlement_fee:
    #             raise ValidationError(
    #                 "Please enter settlement fee."
    #             )

    #         if not rec.settlement_fee_account_id:
    #             raise ValidationError(
    #                 "Please select settlement fee account."
    #             )

    #         if not rec.settlement_date:
    #             raise ValidationError(
    #                 "Please enter settlement date."
    #             )

    #         rec.state = 'settled'
    # def action_settle(self):

    #     for rec in self:

    #         if rec.state != 'utilized':
    #             raise ValidationError(
    #                 "Only utilized LC can be settled."
    #             )

    #     # =========================
    #     # VALIDATIONS
    #     # =========================

    #         if not rec.settlement_fee:
    #             raise ValidationError(
    #                 "Please enter settlement fee."
    #             )

    #         if not rec.settlement_fee_account_id:
    #             raise ValidationError(
    #                 "Please select settlement fee account."
    #             )

    #         if not rec.settlement_vat_account_id:
    #             raise ValidationError(
    #                 "Please select settlement VAT account."
    #             )

    #         if not rec.settlement_date:
    #             raise ValidationError(
    #                 "Please enter settlement date."
    #             )

    #         bank_account = rec.bank_journal_id.default_account_id

    #         if not bank_account:
    #             raise ValidationError(
    #                 "Bank journal missing default account."
    #         )

    #     # =========================
    #     # TOTAL CREDIT
    #     # =========================

    #         total_credit = (
    #             rec.settlement_fee
    #             + rec.settlement_tax_amount
    #         )

    #     # =========================
    #     # ACCOUNTING ENTRY
    #     # =========================

    #         move = self.env['account.move'].create({

    #             'move_type': 'entry',
    #             'journal_id': rec.bank_journal_id.id,

    #             'line_ids': [

    #             # ---------------------------------
    #             # SETTLEMENT FEE
    #             # ---------------------------------

    #                 (0, 0, {
    #                     'name': f"LC Settlement Fee - {rec.name}",
    #                     'account_id': rec.settlement_fee_account_id.id,
    #                     'debit': rec.settlement_fee,
    #                     'credit': 0.0,
    #                 }),

    #             # ---------------------------------
    #             # SETTLEMENT TAX
    #             # ---------------------------------

    #                 (0, 0, {
    #                     'name': f"LC Settlement Tax - {rec.name}",
    #                     'account_id': rec.settlement_tax_account_id.id,
    #                     'debit': rec.settlement_tax_amount,
    #                     'credit': 0.0,
    #                 }),

    #             # ---------------------------------
    #             # BANK CREDIT
    #             # ---------------------------------

    #                 (0, 0, {
    #                     'name': f"LC Settlement - {rec.name}",
    #                     'account_id': bank_account.id,
    #                     'debit': 0.0,
    #                     'credit': total_credit,
    #                 }),
    #             ]
    #         })

    #         move.action_post()

    #         rec.write({
    #             'state': 'settled',
    #             'settlement_move_id': move.id,
    #         })

    # # def action_close(self):
    # #     for rec in self:
    # #         rec.state = 'closed'
    # def action_settle(self):

    #     for rec in self:
    #         if rec.state != 'utilized':
    #             raise ValidationError(
    #                 "Only utilized LC can be settled."
    #             )
    #         if not rec.settlement_currency_amount:
    #             rec.settlement_currency_amount = (
    #             rec.remaining_amount
    #         )
    #         # =========================
    #         # VALIDATIONS
    #         # =========================

    #         if not rec.settlement_fee:
    #             raise ValidationError(
    #                 "Please enter settlement fee."
    #             )

    #         if not rec.settlement_fee_account_id:
    #             raise ValidationError(
    #                 "Please select settlement fee account."
    #             )

    #         if not rec.settlement_tax_account_id:
    #             raise ValidationError(
    #                 "Please select settlement tax account."
    #             )

    #         if not rec.settlement_date:
    #             raise ValidationError(
    #                 "Please enter settlement date."
    #             )

    #         bank_account = rec.bank_journal_id.default_account_id

    #         if not bank_account:
    #             raise ValidationError(
    #                 "Bank journal missing default account."
    #             )

    #         # =========================
    #         # FETCH CURRENT FX RATE
    #         # =========================

    #         # company_currency = self.env.company.currency_id

    #         # settlement_rate = self.env[
    #         #     'res.currency'
    #         # ]._get_conversion_rate(
    #         #     rec.currency_id,
    #         #     company_currency,
    #         #     self.env.company,
    #         #     fields.Date.today()
    #         # )
    #         if float_is_zero(rec.settlement_rate, precision_digits=6):
    #             company_currency = self.env.company.currency_id
    #             settlement_rate = self.env['res.currency']._get_conversion_rate(
    #                 rec.currency_id,
    #                 company_currency,
    #                 self.env.company,
    #                 rec.settlement_date or fields.Date.today()
    #             )
    #             rec.settlement_rate = settlement_rate

    #         rec.settlement_rate = settlement_rate

    #         # =========================
    #         # TOTAL CREDIT
    #         # =========================

    #         total_credit = (
    #             rec.settlement_fee
    #             + rec.settlement_tax_amount
    #         )

    #         # =========================
    #         # ACCOUNTING ENTRY
    #         # =========================

    #         move = self.env['account.move'].create({
    #             'move_type': 'entry',
    #             'journal_id': rec.bank_journal_id.id,
    #             'line_ids': [
    #                 # ---------------------------------
    #                 # SETTLEMENT FEE
    #                 # ---------------------------------

    #                 (0, 0, {
    #                     'name': f"LC Settlement Fee - {rec.name}",
    #                     'account_id': rec.settlement_fee_account_id.id,
    #                     'debit': rec.settlement_fee,
    #                     'credit': 0.0,
    #                 }),

    #                 # ---------------------------------
    #                 # SETTLEMENT TAX
    #                 # ---------------------------------

    #                 (0, 0, {
    #                     'name': f"LC Settlement Tax - {rec.name}",
    #                     'account_id': rec.settlement_tax_account_id.id,
    #                     'debit': rec.settlement_tax_amount,
    #                     'credit': 0.0,
    #                 }),

    #                 # ---------------------------------
    #                 # BANK CREDIT
    #                 # ---------------------------------
                    
    #                 (0, 0, {
    #                     'name': f"LC Settlement - {rec.name}",
    #                     'account_id': bank_account.id,
    #                     'debit': 0.0,
    #                     'credit': total_credit,
    #                 }),
    #             ]
    #         })

    #         move.action_post()

    #         rec.write({
    #             'state': 'settled',
    #             'settlement_move_id': move.id,
    #         })
    def action_settle(self):
        for rec in self:
            if rec.state != 'utilized':
                raise ValidationError("Only utilized LC can be settled.")

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

    
    # def action_close(self):
    #     for rec in self:

    #         if not rec.can_close:
    #             raise ValidationError(
    #                 "LC cannot be closed yet."
    #             )
    #         rec.state = 'closed'
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
    # -------------------------
    # USAGE CALCULATION
    # -------------------------
    # @api.depends('purchase_ids.amount_total', 'purchase_ids.state')
    # def _compute_used_amount(self):
    #     for rec in self:
    #         total = 0.0
    #         for po in rec.purchase_ids:
    #             if po.state in ('purchase', 'done'):
    #                 total += po.amount_total

    #         rec.used_amount = total

    #         # 🔥 AUTO STATE LOGIC INSIDE COMPUTE (BEST PRACTICE)
    #         # if rec.state not in ('draft', 'closed'):
    #         #     if rec.used_amount <= 0:
    #         #         rec.state = 'open'
    #         #     elif rec.used_amount < rec.amount:
    #         #         rec.state = 'utilized'
    #         #     else:
    #         #         rec.state = 'closed'
    #         #         if rec.state not in ('draft', 'settled', 'closed'):

           
    # # -------------------------
    # # AUTO STATE UPDATE
    # # -------------------------
    # # @api.depends('used_amount', 'amount')
    # # def _compute_state_auto(self):
    # #     for rec in self:
    # #         if rec.state in ('draft', 'closed'):
    # #             continue

    # #         if rec.used_amount <= 0:
    # #             rec.state = 'open'
    # #         elif rec.used_amount < rec.amount:
    # #             rec.state = 'utilized'
    # #         elif rec.used_amount >= rec.amount:
    # #             rec.state = 'closed'
    
    # @api.depends('purchase_ids.amount_total', 'purchase_ids.state')
    # def _compute_used_amount(self):
    #     for rec in self:
    #         total = 0.0
    #         for po in rec.purchase_ids:
    #             if po.state in ('purchase', 'done'):
    #                 # total += po.amount_total
    #                 # total += po.amount_total_currency
    #                 total += po.amount_total
    #         rec.used_amount = total

    #         # =========================
    #         # AUTO STATE UPDATE
    #         # =========================
    #         # Never touch finalized states
    #         if rec.state in ('draft', 'settled', 'closed'):
    #             continue

    #         # No PO linked yet
    #         if rec.used_amount <= 0:
    #             rec.state = 'open'
    #         # PO linked / LC being used
    #         elif rec.used_amount > 0:
    #             rec.state = 'utilized'
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
    # -------------------------
    # REMAINING AMOUNT CALCULATION  
    # -------------------------
    # @api.depends('amount', 'used_amount')
    # def _compute_remaining_amount(self):
    #     for rec in self:
    #         rec.remaining_amount = rec.amount - rec.used_amount

    # -------------------------
    # MARGIN CALCULATION
    # -------------------------
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
    # @api.depends(
    # 'settlement_currency_amount',
    # 'settlement_rate'
    # )
    # def _compute_settlement_etb(self):

    #     for rec in self:

    #         rec.settlement_etb_amount = (
    #             rec.settlement_currency_amount
    #             * rec.settlement_rate
    #         )
    # @api.onchange('currency_id')
    # def _onchange_currency_id(self):
    #     company_currency = self.env.company.currency_id

    #     if self.currency_id and self.currency_id != company_currency:
    #         rate = self.env['res.currency']._get_conversion_rate(
    #             self.currency_id,
    #             company_currency,
    #             self.env.company,
    #             fields.Date.today()
    #         )

    #         self.exchange_rate = rate

    #     else:
    #         self.exchange_rate = 1.0
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

    # @api.depends(
    # 'amount',
    # 'opening_rate',
    # 'settlement_rate',
    # 'lc_type_id.margin_percentage'
    # )
    # def _compute_fx_gain_loss(self):
    #     for rec in self:
    #         if not rec.opening_rate or not rec.settlement_rate:
    #             rec.fx_gain_loss = 0.0
    #             continue

    #         exposed_percentage = (
    #             100 - rec.lc_type_id.margin_percentage
    #         ) / 100
    #         exposed_amount = (
    #             rec.settlement_currency_amount
    #             * exposed_percentage
    #         )

    #         rec.fx_gain_loss = (
    #             rec.settlement_rate
    #             - rec.opening_rate
    #         ) * exposed_amount
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
    
    # @api.depends('purchase_ids.invoice_ids')
    # def _compute_vendor_bills(self):
    #     for rec in self:
    #         bills = self.env['account.move']
    #         for po in rec.purchase_ids:
    #             bills |= po.invoice_ids
    #         rec.vendor_bill_ids = bills
    #         rec.bill_count = len(bills)
    # @api.depends('state', 'remaining_amount', 'vendor_bill_ids.state')
    # def _compute_can_close(self):
    #     for rec in self:
    #         rec.can_close = (
    #             rec.state == 'settled'
    #             and float_is_zero(
    #                 rec.remaining_amount, 
    #                 precision_rounding=rec.currency_id.rounding
    #             )
    #             and bool(rec.vendor_bill_ids)                     # Bills must exist
    #             and all(bill.state == 'posted' for bill in rec.vendor_bill_ids)  # All posted
    #         )
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
    @api.depends('amount', 'billed_amount')
    def _compute_remaining_amount(self):
        for rec in self:
            rec.remaining_amount = rec.amount - rec.billed_amount


    # ====================== VENDOR BILLS ======================
    @api.depends('purchase_ids.invoice_ids')
    def _compute_vendor_bills(self):
        for rec in self:
            bills = self.env['account.move']
            for po in rec.purchase_ids:
                bills |= po.invoice_ids
            rec.vendor_bill_ids = bills
            rec.bill_count = len(bills)


    # ====================== CAN CLOSE ======================
    @api.depends('state', 'remaining_amount', 'vendor_bill_ids.state')
    def _compute_can_close(self):
        for rec in self:
            rec.can_close = (
                rec.state == 'settled'
                and float_is_zero(
                    rec.remaining_amount, 
                    precision_rounding=rec.currency_id.rounding
                )
                and bool(rec.vendor_bill_ids)
                and all(bill.state == 'posted' for bill in rec.vendor_bill_ids)
            )
   