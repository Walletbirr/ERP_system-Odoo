from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

# LC states in which a bill may be posted against the LC.
LC_BILL_STATES = ('open', 'utilized', 'settled')


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------------
    # LC link
    # ------------------------------------------------------------------
    x_lc_id = fields.Many2one(
        'lc.management', string="Letter of Credit",
        compute='_compute_x_lc_id', store=True, index=True,
        help="The LC of the purchase order(s) this vendor bill belongs to.")
    x_is_lc_bill = fields.Boolean(
        string="LC Bill", copy=False, readonly=True, index=True,
        help="Set when the bill is posted against an LC. The payable is "
             "then replaced by the LC's GIT account and the bill is paid "
             "only by LC settlement, never by a normal payment. Bills "
             "posted before this behaviour existed are left untouched.")
    x_lc_line_ids = fields.One2many(
        'lc.settlement.line', 'vendor_bill_id', string="LC Settlements",
        readonly=True)
    x_lc_settled_amount = fields.Monetary(
        string="Settled by LC", currency_field='currency_id',
        compute='_compute_x_lc_settlement', store=True)
    x_lc_unsettled_amount = fields.Monetary(
        string="Not Yet Settled", currency_field='currency_id',
        compute='_compute_x_lc_settlement', store=True)

    @api.depends('move_type',
                 'invoice_line_ids.display_type',
                 'invoice_line_ids.purchase_line_id.order_id.lc_id')
    def _compute_x_lc_id(self):
        for move in self:
            lcs = self.env['lc.management']
            if move.move_type == 'in_invoice':
                lcs = move.invoice_line_ids.filtered(
                    lambda l: l.display_type == 'product'
                ).purchase_line_id.order_id.lc_id
            move.x_lc_id = lcs[:1]

    @api.depends('x_lc_line_ids.state', 'x_lc_line_ids.amount_to_settle',
                 'x_lc_line_ids.lc_currency_id', 'amount_total', 'currency_id',
                 'x_lc_id.lc_type_id.margin_percentage')
    def _compute_x_lc_settlement(self):
        for move in self:
            # The margin was paid at LC opening, so it already covers that
            # share of the bill; settlements pay the rest.
            margin = move.amount_total * (
                move.x_lc_id.lc_type_id.margin_percentage or 0.0) / 100.0 \
                if move.x_lc_id else 0.0
            settled = margin + sum(
                l.amount_to_settle for l in move.x_lc_line_ids
                if l.state == 'confirmed'
                and l.lc_currency_id == move.currency_id)
            move.x_lc_settled_amount = settled
            move.x_lc_unsettled_amount = max(move.amount_total - settled, 0.0)

    # ------------------------------------------------------------------
    # Posting: the LC's GIT account replaces the payable
    # ------------------------------------------------------------------
    def _lc_bill_check_postable(self):
        for move in self:
            product_lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product')
            if product_lines.filtered(lambda l: not l.purchase_line_id):
                raise UserError(_(
                    "%s is a bill against a Letter of Credit, so every "
                    "product line must come from a purchase order on that "
                    "LC. Remove or move the other lines.",
                    move.display_name))
            lcs = product_lines.purchase_line_id.order_id.lc_id
            if len(lcs) != 1:
                raise UserError(_(
                    "%s mixes purchase orders from different Letters of "
                    "Credit. Create one bill per LC.", move.display_name))
            lc = lcs
            if lc.state not in LC_BILL_STATES:
                raise UserError(_(
                    "Letter of Credit %(lc)s is not open, so bill %(bill)s "
                    "cannot be posted against it.",
                    lc=lc.name, bill=move.display_name))
            if not lc.opening_fee_account_id:
                raise UserError(_(
                    "Letter of Credit %s has no GIT Account.", lc.name))
            if move.currency_id != lc.currency_id:
                raise UserError(_(
                    "Bill %(bill)s is in %(bc)s but LC %(lc)s is in %(lcc)s. "
                    "An LC bill must be in the LC currency.",
                    bill=move.display_name, bc=move.currency_id.name,
                    lc=lc.name, lcc=lc.currency_id.name))
            if float_compare(
                    move.x_lc_settled_amount, move.amount_total,
                    precision_rounding=move.currency_id.rounding) > 0:
                raise UserError(_(
                    "Bill %s is smaller than what the LC has already "
                    "settled against it.", move.display_name))

    def _lc_bill_apply_git_account(self):
        """Put the LC's GIT account on the payment-term line(s)."""
        ctx = dict(skip_invoice_sync=True, dynamic_unlink=True)
        for move in self:
            account = move.x_lc_id.opening_fee_account_id
            lines = move.line_ids.filtered(
                lambda l: l.display_type == 'payment_term'
                and l.account_id != account)
            if lines:
                lines.with_context(**ctx).write({'account_id': account.id})

    def _lc_bill_link_settlements(self):
        """Attach the freshly posted bill to the open settlement tranches of
        its purchase orders. Only when the PO has exactly one LC bill;
        otherwise the accountant picks the bill on the tranche."""
        for move in self:
            lc = move.x_lc_id
            for po in move.invoice_line_ids.purchase_line_id.order_id:
                bills = po.invoice_ids.filtered(
                    lambda b: b.state == 'posted' and b.x_is_lc_bill
                    and b.x_lc_id == lc)
                if len(bills) != 1:
                    continue
                lines = lc.settlement_line_ids.filtered(
                    lambda l: l.purchase_order_id == po
                    and l.state in ('draft', 'submitted')
                    and not l.vendor_bill_id)
                if lines:
                    lines.write({'vendor_bill_id': bills.id})

    def _post(self, soft=True):
        lc_bills = self.filtered(
            lambda m: m.move_type == 'in_invoice' and m.state == 'draft'
            and m.x_lc_id)
        if lc_bills:
            lc_bills._lc_bill_check_postable()
            lc_bills._lc_bill_apply_git_account()
            lc_bills.write({'x_is_lc_bill': True})
        res = super()._post(soft=soft)
        lc_bills._lc_bill_link_settlements()
        return res

    # ------------------------------------------------------------------
    # Guards: only LC settlement may pay or undo these bills
    # ------------------------------------------------------------------
    def _lc_bill_block_payment(self):
        lc_bills = self.filtered('x_is_lc_bill')
        if lc_bills:
            raise UserError(_(
                "%s is a Letter of Credit bill. It is paid by LC "
                "settlement, not by a payment. Confirm the settlement "
                "on the LC instead.",
                ", ".join(lc_bills.mapped('display_name'))))

    def action_register_payment(self, *args, **kwargs):
        self._lc_bill_block_payment()
        return super().action_register_payment(*args, **kwargs)

    def action_force_register_payment(self, *args, **kwargs):
        self._lc_bill_block_payment()
        return super().action_force_register_payment(*args, **kwargs)

    def button_cancel(self):
        for move in self.filtered('x_is_lc_bill'):
            if move.x_lc_line_ids.filtered(lambda l: l.state == 'confirmed'):
                raise UserError(_(
                    "%s has confirmed LC settlements. Cancel the LC "
                    "settlement first, then cancel the bill.",
                    move.display_name))
        return super().button_cancel()

    def _reverse_moves(self, default_values_list=None, cancel=False):
        if any(m.x_is_lc_bill and m.state == 'posted' for m in self):
            raise UserError(_(
                "A credit note cannot be made on a Letter of Credit bill. "
                "Reset the bill to draft instead (after cancelling its LC "
                "settlement, if it has one)."))
        return super()._reverse_moves(
            default_values_list=default_values_list, cancel=cancel)
