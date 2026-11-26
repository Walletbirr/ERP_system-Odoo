from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # NOTE: `is_import` is defined in the shipment_tracking module
    # (models/purchase_order.py), which this module depends on. It's not
    # redefined here - lc_management only adds the LC-specific field and
    # logic on top of that existing "is this an import order" flag.

    lc_settlement_line_ids = fields.One2many(
        'lc.settlement.line', 'purchase_order_id',
        string="LC Settlements", readonly=True)

    lc_currency_id = fields.Many2one(related='lc_id.currency_id')
    lc_margin_pct = fields.Float(
        string="LC Margin %", related='lc_id.lc_type_id.margin_percentage')
    lc_amount = fields.Monetary(
        string="LC Amount", related='lc_id.amount',
        currency_field='lc_currency_id')
    lc_available_amount = fields.Monetary(
        string="LC Available", related='lc_id.available_amount',
        currency_field='lc_currency_id')
    lc_po_margin = fields.Monetary(
        string="Margin Paid for This PO", currency_field='lc_currency_id',
        compute='_compute_lc_po_figures',
        help="The part of the margin paid at LC opening that belongs to "
             "this purchase: LC margin % x this PO's total.")
    lc_po_balance = fields.Monetary(
        string="Balance to Settle", currency_field='lc_currency_id',
        compute='_compute_lc_po_figures',
        help="What is left to pay the bank for this purchase after its "
             "margin. This is the amount split into settlement tranches.")

    lc_id = fields.Many2one(
        'lc.management',
        string="Letter of Credit",
        domain="[('partner_id', '=', partner_id), ('state', 'in', ('open', 'utilized')), ('available_amount', '>', 0)]"
    )

    # -------------------------
    # ONCHANGE: IMPORT TOGGLE
    # -------------------------
    @api.onchange('is_import')
    def _onchange_is_import(self):
        # Switching back to "local" clears any LC that was selected while
        # the order was flagged as an import, so it can't linger unseen.
        if not self.is_import:
            self.lc_id = False

    # -------------------------
    # ONCHANGE: LC SELECTION
    # -------------------------
    @api.onchange('lc_id')
    def _onchange_lc_id(self):
        if self.lc_id:
            lc = self.lc_id

            if lc.state not in ('open', 'utilized'):
                raise ValidationError("Only an Open or Utilized LC can be selected.")

            # Compare with what the LC can still take (its amount less the
            # purchase orders already on it) - NOT with what is left to pay
            # the bank, which already excludes the margin paid at opening.
            needed = self.amount_total
            if needed and self.currency_id and self.currency_id != lc.currency_id:
                needed = self.currency_id._convert(
                    needed, lc.currency_id, self.company_id or self.env.company,
                    fields.Date.context_today(self))
            if needed and lc.currency_id.compare_amounts(needed, lc.available_amount) > 0:
                raise ValidationError(
                    f"Selected LC cannot take this purchase.\n"
                    f"LC amount: {lc.amount}\n"
                    f"Available for new purchases: {lc.available_amount}"
                )

            self.partner_id = lc.partner_id

    # -------------------------
    # ONCHANGE: VENDOR CHANGE
    # -------------------------
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.lc_id and self.partner_id:
            if self.lc_id.partner_id != self.partner_id:
                raise ValidationError(
                    "Selected LC does not belong to this supplier."
                )

    # -------------------------
    # CONFIRMATION VALIDATION
    # -------------------------
    def button_confirm(self):
        for po in self:
            if not po.is_import:
                # Local purchase: no LC involved, nothing to validate.
                continue

            if not po.lc_id:
                raise ValidationError("Please assign LC before confirming.")

            lc = po.lc_id

            if lc.state not in ('open', 'utilized'):
                raise ValidationError("LC is not active.")

            if po.partner_id != lc.partner_id:
                raise ValidationError(
                    f"LC is issued for {lc.partner_id.name}, "
                    f"but this purchase is for {po.partner_id.name}"
                )

            needed = po.amount_total
            if po.currency_id != lc.currency_id:
                needed = po.currency_id._convert(
                    needed, lc.currency_id, po.company_id,
                    fields.Date.context_today(po))
            if lc.currency_id.compare_amounts(needed, lc.available_amount) > 0:
                raise ValidationError(
                    f"LC balance exceeded!\nAvailable for new purchases: "
                    f"{lc.available_amount}"
                )

        res = super().button_confirm()

        for po in self:
            if po.is_import and po.lc_id:
                po.lc_id._compute_used_amount()

        self._lc_sync_margin_payment()
        return res

    # -------------------------
    # PAYMENTS BUTTON (purchase_bank_payment)
    # -------------------------
    @api.depends('lc_id', 'amount_total', 'currency_id',
                 'lc_id.lc_type_id.margin_percentage')
    def _compute_lc_po_figures(self):
        for po in self:
            if not po.lc_id:
                po.lc_po_margin = 0.0
                po.lc_po_balance = 0.0
                continue
            lc = po.lc_id
            total = po.amount_total
            if po.currency_id and po.currency_id != lc.currency_id:
                total = po.currency_id._convert(
                    total, lc.currency_id, po.company_id or self.env.company,
                    fields.Date.context_today(po))
            margin = lc.currency_id.round(
                total * (lc.lc_type_id.margin_percentage or 0.0) / 100.0)
            po.lc_po_margin = margin
            po.lc_po_balance = total - margin

    def _lc_margin_amount(self):
        """Margin this PO holds at the bank, in the PO currency:
        LC margin % x PO total. Same share the settlement later deducts."""
        self.ensure_one()
        lc = self.lc_id
        amount = self.amount_total
        if self.currency_id != lc.currency_id:
            amount = self.currency_id._convert(
                amount, lc.currency_id, self.company_id,
                fields.Date.context_today(self))
        margin = amount * lc.lc_type_id.margin_percentage / 100.0
        if self.currency_id != lc.currency_id:
            margin = lc.currency_id._convert(
                margin, self.currency_id, self.company_id,
                fields.Date.context_today(self))
        return self.currency_id.round(margin)

    def _lc_sync_margin_payment(self):
        """Keep one 'LC margin' payment on the PO: posted by the LC opening,
        so the PO shows it first, before any settlement."""
        Payment = self.env['purchase.bank.payment'].with_context(bp_sync=True)
        for po in self:
            rec = Payment.search([('purchase_id', '=', po.id),
                                  ('source', '=', 'lc_margin')], limit=1)
            lc = po.lc_id
            active = bool(
                po.is_import and lc and po.x_direct_pay
                and po.state in ('purchase', 'done')
                and lc.state in ('open', 'utilized', 'settled')
                and lc.opening_move_id)
            amount = po._lc_margin_amount() if active else 0.0
            if not active or po.currency_id.is_zero(amount):
                if rec and rec.state != 'cancelled':
                    rec.write({'state': 'cancelled'})
                continue
            rate = lc.opening_rate or lc.exchange_rate
            vals = {
                'amount': amount,
                'date': lc.opening_move_id.date,
                'journal_id': lc.bank_journal_id.id,
                'git_account_id': lc.opening_fee_account_id.id,
                'move_id': lc.opening_move_id.id,
                'memo': f"LC margin paid at opening ({lc.name}, "
                        f"{lc.lc_type_id.margin_percentage:g}%)",
                'lc_id': lc.id,
                'external_amount_company':
                    po.company_id.currency_id.round(amount * rate),
                'state': 'posted',
            }
            if rec:
                rec.write(vals)
            else:
                Payment.create({**vals, 'source': 'lc_margin',
                                'purchase_id': po.id})

    def button_cancel(self):
        res = super().button_cancel()
        self._lc_sync_margin_payment()
        return res

    def write(self, vals):
        res = super().write(vals)
        if 'lc_id' in vals:
            self._lc_sync_margin_payment()
        return res

    def action_new_bank_payment(self):
        self.ensure_one()
        if self.lc_id:
            raise ValidationError(
                "This purchase is paid through its Letter of Credit. "
                "Payments appear here when the LC settlement is confirmed."
            )
        return super().action_new_bank_payment()
