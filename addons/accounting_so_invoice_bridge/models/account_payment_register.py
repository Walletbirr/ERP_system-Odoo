import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    # Several banks on the approved proof: the dialog's Journal and Amount
    # become one row per bank (see the view); the Amount is their total and
    # "Create Payment" registers ONE payment whose journal entry has one
    # bank line per row (see account_payment.py). With one bank (or none)
    # nothing here is active and the dialog is the standard one.
    bridge_multi_bank = fields.Boolean()
    bridge_bank_line_ids = fields.One2many(
        'bridge.payment.register.bank', 'wizard_id', string='Banks')

    @api.model
    def _proof_bank_lines_for_moves(self, moves):
        """Bank rows (bank + amount) of the most recently approved proof of
        the order behind this invoice, only when that proof has SEVERAL
        banks, the dialog is for one invoice and the amounts are in the
        invoice currency. Otherwise empty (= standard dialog)."""
        empty = self.env['sale.order.payment.proof.bank']
        moves = moves.filtered(
            lambda m: m.move_type == 'out_invoice').sudo()
        if len(moves) != 1:
            return empty
        proofs = moves.x_sale_order_ids.payment_proof_ids.filtered(
            lambda p: p.state == 'approved' and p.payment_bank_ids)
        if not proofs:
            return empty
        banks = proofs.sorted(
            lambda p: (p.reviewed_date or p.create_date, p.id)
        )[-1].payment_bank_ids
        if len(banks) < 2 or any(
                b.currency_id != moves.currency_id for b in banks):
            return empty
        return banks

    @api.model
    def _proof_journal_for_moves(self, moves):
        """Journal the accountant chose when approving the payment proof of
        the order(s) behind these customer invoices. With several approved
        proofs the most recently approved one wins. Empty if none or if the
        journal can not be used for this payment."""
        moves = moves.filtered(
            lambda m: m.move_type == 'out_invoice').sudo()
        proofs = moves.x_sale_order_ids.payment_proof_ids.filtered(
            lambda p: p.state == 'approved' and p.payment_journal_id)
        if not proofs:
            return self.env['account.journal']
        journal = proofs.sorted(
            lambda p: (p.reviewed_date or p.create_date, p.id)
        )[-1].payment_journal_id
        if journal.type not in ('bank', 'cash') \
                or journal.company_id != moves[:1].company_id:
            return self.env['account.journal']
        lines_of = getattr(journal, '_get_available_payment_method_lines', None)
        if lines_of and not lines_of('inbound'):
            return self.env['account.journal']
        return journal

    @api.model
    def default_get(self, fields_list):
        """Main hook: the Pay dialog opens with the proof's journal already
        in place (a default is never overwritten by the computed one)."""
        res = super().default_get(fields_list)
        if 'journal_id' not in fields_list:
            return res
        try:
            ctx = self.env.context
            active_ids = ctx.get('active_ids') or []
            moves = self.env['account.move']
            if ctx.get('active_model') == 'account.move':
                moves = moves.browse(active_ids).exists()
            elif ctx.get('active_model') == 'account.move.line':
                moves = self.env['account.move.line'].browse(
                    active_ids).exists().move_id
            journal = self._proof_journal_for_moves(moves) if moves \
                else self.env['account.journal']
            if journal:
                res['journal_id'] = journal.id
            banks = self._proof_bank_lines_for_moves(moves) if moves \
                else self.env['sale.order.payment.proof.bank']
            if banks:
                res['journal_id'] = banks[0].journal_id.id
                res['bridge_multi_bank'] = True
                res['bridge_bank_line_ids'] = [(0, 0, {
                    'journal_id': bank.journal_id.id,
                    'amount': bank.amount,
                }) for bank in banks]
                if 'amount' in fields_list:
                    res['amount'] = sum(banks.mapped('amount'))
        except Exception:
            _logger.exception(
                "accounting_so_invoice_bridge: could not preselect the "
                "payment-proof journal - the standard journal is kept.")
        return res

    @api.depends('available_journal_ids')
    def _compute_journal_id(self):
        """Backup hook for flows where the journal is computed instead of
        coming from the defaults."""
        super()._compute_journal_id()
        for wizard in self:
            try:
                journal = self._proof_journal_for_moves(
                    wizard.line_ids.move_id)
            except Exception:
                _logger.exception("payment-proof journal lookup failed")
                continue
            if journal and journal in wizard.available_journal_ids:
                wizard.journal_id = journal

    @api.onchange('bridge_bank_line_ids')
    def _onchange_bridge_bank_line_ids(self):
        """The Amount of the dialog is the total of the bank rows, so the
        standard "Payment difference" compares the TOTAL with the invoice."""
        for wizard in self:
            lines = wizard.bridge_bank_line_ids.filtered('journal_id')
            if wizard.bridge_multi_bank and lines:
                # Journal first: changing it can recompute the amount.
                if wizard.journal_id != lines[0].journal_id:
                    wizard.journal_id = lines[0].journal_id
                wizard.amount = sum(lines.mapped('amount'))

    def _bridge_bank_rows(self):
        """The bank rows of the dialog that are filled in, validated."""
        self.ensure_one()
        rows = self.bridge_bank_line_ids.sorted(
            lambda r: (r.sequence, r.id)).filtered('journal_id')
        if not rows:
            raise UserError(_("Add at least one bank."))
        for row in rows:
            if self.currency_id.compare_amounts(row.amount, 0) <= 0:
                raise UserError(_(
                    "Enter the amount received in %s.",
                    row.journal_id.display_name))
        if len(rows.journal_id) != len(rows):
            raise UserError(_(
                "Each bank can only be listed once. Put the total received "
                "in a bank on a single row."))
        return rows

    def _bridge_sync_banks(self):
        """Server side, the dialog's Journal and Amount always follow the
        bank rows (the browser does not send the read-only Amount)."""
        self.ensure_one()
        rows = self._bridge_bank_rows()
        # Journal first: changing it can recompute the currency and amount.
        if self.journal_id != rows[0].journal_id:
            self.journal_id = rows[0].journal_id
        total = sum(rows.mapped('amount'))
        if self.currency_id.compare_amounts(self.amount, total):
            self.amount = total
        return rows

    def action_create_payments(self):
        if self.bridge_multi_bank:
            self._bridge_sync_banks()
        return super().action_create_payments()

    def _create_payment_vals_from_wizard(self, batch_result):
        """ONE payment for the whole deposit: the standard payment values,
        plus the bank rows (only when there really are several banks; one
        row is just a normal payment in that bank)."""
        vals = super()._create_payment_vals_from_wizard(batch_result)
        # Carry the invoice Reference (which comes from the sales order) to
        # the payment Reference of multi_line_payment.
        refs = []
        for ref in batch_result['lines'].move_id.mapped('cim_reference'):
            if ref and ref not in refs:
                refs.append(ref)
        if refs:
            vals['voucher_reference'] = ', '.join(refs)
        if self.bridge_multi_bank:
            rows = self._bridge_bank_rows()
            if len(rows) > 1:
                vals['bridge_bank_line_ids'] = [Command.create({
                    'sequence': index,
                    'journal_id': row.journal_id.id,
                    'amount': row.amount,
                }) for index, row in enumerate(rows, 1)]
        return vals

    def _create_payments(self):
        payments = super()._create_payments()
        if self.bridge_multi_bank \
                and len(self._bridge_bank_rows()) > 1 \
                and not payments.bridge_bank_line_ids:
            # Odoo did not use the editable dialog (several installments of
            # one invoice, paid separately): never lose the banks silently.
            raise UserError(_(
                "Several banks can only be used when the invoice is paid in "
                "one payment. Choose \"Create one payment for all invoices\" "
                "or pay the installments one by one."))
        return payments


class BridgePaymentRegisterBank(models.TransientModel):
    _name = 'bridge.payment.register.bank'
    _description = 'Pay dialog - bank row'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'account.payment.register', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    journal_id = fields.Many2one(
        'account.journal', string='Bank / Journal', required=True,
        domain="[('type', 'in', ('bank', 'cash'))]")
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    amount = fields.Monetary(
        string='Amount', required=True, currency_field='currency_id')
