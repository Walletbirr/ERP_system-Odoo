from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero, float_compare


class LCSettlementLine(models.Model):
    _name = 'lc.settlement.line'
    _description = 'LC Settlement Line'
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
    all_tranche_ids = fields.Many2many(
        'lc.settlement.line',
        compute='_compute_po_rollup',
        string="All Tranches (this PO)",
        help="This line plus every line it was split into - the complete picture "
             "of how this PO's settlement was paid, in order.",
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, readonly=True)

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
    # MARGIN RELEASE (PROPORTIONAL, CAPPED)
    # =========================================================
    margin_released_this_line = fields.Monetary(
        string="Margin Released (this tranche)",
        currency_field='company_currency_id',
        compute='_compute_margin_released_this_line',
        store=True
    )
    fx_gain_loss_this_line = fields.Monetary(
        string="FX Gain/Loss (this tranche)",
        currency_field='company_currency_id',
        compute='_compute_margin_released_this_line',
        store=True
    )

    # =========================================================
    # ACCOUNTING MOVES PRODUCED ON CONFIRM
    # =========================================================
    settlement_move_id = fields.Many2one(
        'account.move', string="Settlement Fee/VAT Entry", readonly=True
    )
    release_move_id = fields.Many2one(
        'account.move', string="Margin Release Entry", readonly=True
    )

    # =========================================================
    # COMPUTE: PROPORTIONAL MARGIN RELEASE FOR THIS LINE
    # =========================================================
    @api.depends(
        'amount_to_settle',
        'settlement_rate',
        'state',
        'lc_id.amount',
        'lc_id.margin_amount_company_currency',
        'lc_id.opening_rate',
        'lc_id.settlement_line_ids.amount_to_settle',
        'lc_id.settlement_line_ids.state',
    )
    def _compute_margin_released_this_line(self):
        for line in self:
            lc = line.lc_id

            if not lc or float_is_zero(lc.amount, precision_rounding=lc.currency_id.rounding or 0.01):
                line.margin_released_this_line = 0.0
                line.fx_gain_loss_this_line = 0.0
                continue

            # A cancelled line no longer contributes or displays a release amount,
            # regardless of what it held while draft/confirmed.
            if line.state == 'cancelled':
                line.margin_released_this_line = 0.0
                line.fx_gain_loss_this_line = 0.0
                continue

            # Proportional share of margin this tranche represents
            proportion = line.amount_to_settle / lc.amount
            theoretical_release = lc.margin_amount_company_currency * proportion

            # Cap: never release more than what remains unreleased on the LC.
            # Computed deterministically from sibling CONFIRMED lines (excluding
            # self by id), rather than from the mutable lc.margin_released_amount
            # field, so this stays correct no matter how many times or in what
            # order Odoo re-triggers the compute.
            other_confirmed_lines = lc.settlement_line_ids.filtered(
                lambda l: l.id != line.id and l.state == 'confirmed'
            )
            released_by_others = sum(
                (lc.margin_amount_company_currency * (l.amount_to_settle / lc.amount))
                for l in other_confirmed_lines
            )
            released_by_others = min(released_by_others, lc.margin_amount_company_currency)

            remaining_unreleased = max(lc.margin_amount_company_currency - released_by_others, 0.0)

            release_amount = min(theoretical_release, remaining_unreleased)
            line.margin_released_this_line = release_amount

            # FX gain/loss on the margin portion being released this tranche:
            # difference between the rate frozen at opening and this tranche's settlement rate.
            if lc.opening_rate and line.settlement_rate:
                # Convert the released margin (company currency) back to LC currency
                # at opening rate to find the LC-currency principal it represents,
                # then re-value at settlement rate.
                if not float_is_zero(lc.opening_rate, precision_digits=6):
                    margin_lc_currency = release_amount / lc.opening_rate
                    revalued = margin_lc_currency * line.settlement_rate
                    line.fx_gain_loss_this_line = release_amount - revalued
                else:
                    line.fx_gain_loss_this_line = 0.0
            else:
                line.fx_gain_loss_this_line = 0.0

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
    def _compute_po_rollup(self):
        for line in self:
            root = line._get_root_line()

            # Gather every tranche for this PO: the root plus all its
            # splits, recursively (in case a split was itself split again).
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

            confirmed = all_tranches.filtered(lambda t: t.state == 'confirmed')
            cancelled_excluded = all_tranches.filtered(lambda t: t.state != 'cancelled')

            line.all_tranche_ids = all_tranches
            line.po_total_settled = sum(confirmed.mapped('amount_to_settle'))
            line.po_total_amount = sum(cancelled_excluded.mapped('amount_to_settle'))
            line.po_remaining_to_settle = max(line.po_total_amount - line.po_total_settled, 0.0)
            line.po_tranche_count = len(all_tranches.filtered(lambda t: t.state != 'cancelled'))

            lc_currency = line.lc_id.currency_id
            line.po_is_fully_settled = bool(cancelled_excluded) and float_is_zero(
                line.po_remaining_to_settle,
                precision_rounding=lc_currency.rounding if lc_currency else 0.01
            )

    def action_confirm_with_preview(self):
        """Validates this line exactly as action_confirm would, builds a
        plain-text preview of the moves about to post (settlement fee/VAT
        and margin release), and opens a confirmation wizard. Posting only
        happens if the user confirms in that wizard."""
        self.ensure_one()
        line = self
        lc = line.lc_id

        # Run the same checks action_confirm runs, so the preview can never
        # show a wizard for something that would then fail to post.
        if line.state != 'draft':
            raise ValidationError("Only draft settlement lines can be confirmed.")
        if not line.purchase_order_id:
            raise ValidationError("This settlement line has no linked Purchase Order.")
        if line.purchase_order_id.state not in ('purchase', 'done'):
            raise ValidationError(f"Purchase Order {line.purchase_order_id.name} is not confirmed.")
        if line.shipment_id and line.shipment_id.state != 'arrived':
            raise ValidationError(
                f"Shipment {line.shipment_id.reference} is no longer marked as Arrived."
            )
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

        total_credit = line.settlement_fee + line.settlement_vat_amount
        company_currency_name = lc.company_currency_id.name

        preview_lines = []
        if not float_is_zero(total_credit, precision_digits=2):
            preview_lines.append("Settlement Fee/VAT Entry:")
            preview_lines.append(
                f"  Debit  {line.settlement_fee_account_id.name}: "
                f"{line.settlement_fee:,.2f} {company_currency_name}"
            )
            if not float_is_zero(line.settlement_vat_amount, precision_digits=2):
                preview_lines.append(
                    f"  Debit  {line.settlement_vat_account_id.name}: "
                    f"{line.settlement_vat_amount:,.2f} {company_currency_name}"
                )
            preview_lines.append(
                f"  Credit {bank_account.name}: {total_credit:,.2f} {company_currency_name}"
            )

        release_amount = line.margin_released_this_line
        if not float_is_zero(release_amount, precision_digits=2):
            if preview_lines:
                preview_lines.append("")
            preview_lines.append("Margin Release Entry:")
            preview_lines.append(
                f"  Debit  {bank_account.name}: {release_amount:,.2f} {company_currency_name}"
            )
            preview_lines.append(
                f"  Credit {lc.margin_account_id.name}: {release_amount:,.2f} {company_currency_name}"
            )

        if not preview_lines:
            preview_lines.append("No accounting entries will be posted (fee, VAT, and margin release are all zero).")

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

            if line.state != 'draft':
                raise ValidationError("Only draft settlement lines can be confirmed.")

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

            # ===================== SETTLEMENT FEE/VAT MOVE =====================
            total_credit = line.settlement_fee + line.settlement_vat_amount
            settlement_move = False
            if not float_is_zero(total_credit, precision_digits=2):
                settlement_line_vals = [
                    (0, 0, {
                        'name': f"LC Settlement Fee - {lc.name}",
                        'account_id': line.settlement_fee_account_id.id,
                        'debit': line.settlement_fee,
                        'credit': 0.0,
                    }),
                ]
                if line.settlement_vat_account_id and not float_is_zero(
                    line.settlement_vat_amount, precision_digits=2
                ):
                    settlement_line_vals.append((0, 0, {
                        'name': f"LC Settlement VAT - {lc.name}",
                        'account_id': line.settlement_vat_account_id.id,
                        'debit': line.settlement_vat_amount,
                        'credit': 0.0,
                    }))
                settlement_line_vals.append((0, 0, {
                    'name': f"LC Settlement - {lc.name}",
                    'account_id': bank_account.id,
                    'debit': 0.0,
                    'credit': total_credit,
                }))

                settlement_move = self.env['account.move'].create({
                    'move_type': 'entry',
                    'journal_id': lc.bank_journal_id.id,
                    'ref': f"LC Settlement - {lc.name}",
                    'line_ids': settlement_line_vals,
                })
                settlement_move.action_post()
                line.settlement_move_id = settlement_move.id

            # ===================== MARGIN RELEASE MOVE =====================
            release_amount = line.margin_released_this_line
            release_move = False
            if not float_is_zero(release_amount, precision_digits=2):
                release_move = self.env['account.move'].create({
                    'move_type': 'entry',
                    'journal_id': lc.bank_journal_id.id,
                    'ref': f"LC Margin Release - {lc.name}",
                    'line_ids': [
                        (0, 0, {
                            'name': f"LC Margin Release - {lc.name}",
                            'account_id': bank_account.id,
                            'debit': release_amount,
                            'credit': 0.0,
                        }),
                        (0, 0, {
                            'name': f"LC Margin Release - {lc.name}",
                            'account_id': lc.margin_account_id.id,
                            'debit': 0.0,
                            'credit': release_amount,
                        }),
                    ]
                })
                release_move.action_post()
                line.release_move_id = release_move.id

            line.state = 'confirmed'

            # margin_released_amount on the LC recomputes automatically from
            # confirmed settlement lines (see lc._compute_margin_released_amount) -
            # no direct write needed here.

            # Recompute dependent fields then check if the LC can move to 'settled'
            lc._compute_paid_amount()
            lc._compute_remaining_amount()
            lc._refresh_settlement_state()

        if len(self) == 1 and not float_is_zero(self.margin_released_this_line, precision_digits=2):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Margin released",
                    'message': (
                        f"{self.margin_released_this_line:,.2f} "
                        f"{self.company_currency_id.name} released from margin for {self.lc_id.name}."
                    ),
                    'type': 'success',
                    'sticky': False,
                }
            }

    def action_cancel_line(self):
        """Reverse a confirmed line's moves and mark it cancelled. Used by LC cancellation."""
        for line in self:
            if line.state != 'confirmed':
                line.state = 'cancelled'
                continue

            if line.settlement_move_id:
                line.lc_id._reverse_move(line.settlement_move_id)
            if line.release_move_id:
                line.lc_id._reverse_move(line.release_move_id)
                # margin_released_amount on the LC recomputes automatically
                # once line.state flips to 'cancelled' below.

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

    def _split_off_amount(self, split_amount):
        """Shrinks this line's amount_to_settle by split_amount and creates
        a new draft line for that split-off portion, linked back via
        parent_settlement_line_id. Both lines remain independently
        confirmable, each with its own fee/VAT/rate."""
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

        new_line = self.env['lc.settlement.line'].create({
            'lc_id': lc.id,
            'purchase_order_id': self.purchase_order_id.id,
            'shipment_id': self.shipment_id.id,
            'vendor_bill_id': self.vendor_bill_id.id,
            'parent_settlement_line_id': self.id,
            'amount_to_settle': split_amount,
            'settlement_rate': self.settlement_rate,
            'settlement_date': fields.Date.today(),
            'settlement_fee_account_id': self.settlement_fee_account_id.id,
            'settlement_vat_account_id': self.settlement_vat_account_id.id,
            'state': 'draft',
        })

        self.amount_to_settle = remaining_amount

        return new_line

