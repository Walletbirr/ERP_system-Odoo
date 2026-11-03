from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_is_cash_sale = fields.Boolean(
        string='Cash Sale', copy=False, readonly=True, index=True,
        help='Set when the invoice is created from a cash sales order. The '
             'bank(s) approved on the payment proof replace the receivable.')
    x_cash_order_id = fields.Many2one(
        'sale.order', string='Cash Sale Order', copy=False, readonly=True,
        index=True)
    x_cash_bank_line_ids = fields.Many2many(
        'account.move.line', compute='_compute_x_cash_bank_line_ids',
        string='Banks')

    @api.depends('line_ids.display_type', 'line_ids.account_id',
                 'line_ids.balance')
    def _compute_x_cash_bank_line_ids(self):
        for move in self:
            move.x_cash_bank_line_ids = (
                move.line_ids.filtered(lambda l: l.display_type == 'payment_term')
                if move.x_is_cash_sale else self.env['account.move.line'])

    # ------------------------------------------------------------------
    # Banks approved on the payment proof (bridge module)
    # ------------------------------------------------------------------
    def _cash_sale_approved_banks(self):
        """[(journal, amount or None)] from the approved proof(s) of the
        order. None = old-style proof with one journal and no amount."""
        self.ensure_one()
        order = self.x_cash_order_id.sudo()
        proofs = order.payment_proof_ids.filtered(lambda p: p.state == 'approved')
        totals = {}
        for proof in proofs:
            if proof.payment_bank_ids:
                for bank in proof.payment_bank_ids:
                    totals[bank.journal_id] = (
                        (totals.get(bank.journal_id) or 0.0) + bank.amount)
            elif proof.payment_journal_id:
                totals.setdefault(proof.payment_journal_id, None)
        return list(totals.items())

    def _cash_sale_bank_rows(self):
        self.ensure_one()
        rows = self._cash_sale_approved_banks()
        if len(rows) == 1 and rows[0][1] is None:
            rows = [(rows[0][0], self.amount_total)]
        return rows

    def _cash_sale_apply_banks(self, strict):
        """Put the bank account(s) on the payment-term line(s). strict=False
        (draft creation) only sets the account; strict=True (posting) also
        checks the amounts and splits one line per bank."""
        for move in self:
            rows = move._cash_sale_approved_banks()
            if not rows:
                if strict:
                    raise UserError(_(
                        "%s is a cash sale but its payment proof has no "
                        "approved bank.", move.name or move.display_name))
                continue
            for journal, _amount in rows:
                if not journal.default_account_id:
                    raise UserError(_(
                        "Journal %s has no default account.",
                        journal.display_name))
            term_lines = move.line_ids.filtered(
                lambda l: l.display_type == 'payment_term')
            if not term_lines:
                continue
            ctx = dict(skip_invoice_sync=True, dynamic_unlink=True)
            rows = move._cash_sale_bank_rows()
            currency = move.currency_id
            total = sum(a for _j, a in rows)
            if currency.compare_amounts(total, move.amount_total):
                if not strict:
                    # Draft: amounts do not match yet (partial invoice or
                    # not final). Only the first bank account is set; the
                    # split and the check happen when it is posted.
                    term_lines.with_context(**ctx).write(
                        {'account_id': rows[0][0].default_account_id.id})
                    continue
                raise UserError(_(
                    "The approved banks (%(banks)s) do not add up to the "
                    "invoice total (%(total)s). Ask Accounting to approve the "
                    "payment proof again with the right amounts.",
                    banks=formatLang(self.env, total, currency_obj=currency),
                    total=formatLang(self.env, move.amount_total,
                                     currency_obj=currency)))
            first = term_lines[0]
            total_balance = sum(term_lines.mapped('balance'))
            total_amount = sum(term_lines.mapped('amount_currency'))
            company_cur = move.company_id.currency_id
            commands, used = [], 0.0
            for index, (journal, amount) in enumerate(rows):
                if index == len(rows) - 1:
                    balance = total_balance - used
                else:
                    balance = company_cur.round(total_balance * amount / total)
                    used += balance
                vals = {
                    'account_id': journal.default_account_id.id,
                    'name': journal.name,
                    'balance': balance,
                    'amount_currency': (
                        amount if len(rows) > 1 else total_amount),
                }
                if index == 0:
                    commands.append(Command.update(first.id, vals))
                else:
                    vals.update({
                        'move_id': move.id,
                        'display_type': 'payment_term',
                        'partner_id': first.partner_id.id,
                        'currency_id': first.currency_id.id,
                        'date_maturity': first.date_maturity,
                    })
                    commands.append(Command.create(vals))
            extra = term_lines - first
            # delete the old extra lines and write the new split in ONE
            # step, so the entry is never seen unbalanced half-way
            commands += [Command.delete(l.id) for l in extra]
            move.with_context(**ctx).write({'line_ids': commands})

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------
    @staticmethod
    def _cash_sale_is_manual(move):
        """True when the accountant ticked "Manual Journal Items"
        (invoice_lines_editable). Works without that module installed."""
        return bool(getattr(move, 'manual_journal_items', False))

    def _cash_sale_has_custom_account(self):
        """True when the accountant already moved a receivable/bank line to
        an account that is not one of the approved banks (for example the
        customer's own account). That is a deliberate choice: it must never
        be put back to the bank."""
        self.ensure_one()
        rows = self._cash_sale_approved_banks()
        bank_accounts = {j.default_account_id for j, _a in rows if j.default_account_id}
        if not bank_accounts:
            return False
        term_lines = self.line_ids.filtered(lambda l: l.display_type == 'payment_term')
        return any(l.account_id not in bank_accounts for l in term_lines)

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves.filtered(
            lambda m: m.x_is_cash_sale and m.move_type == 'out_invoice'
            and m.state == 'draft')._cash_sale_apply_banks(strict=False)
        return moves

    def _post(self, soft=True):
        cash = self.filtered(
            lambda m: m.x_is_cash_sale and m.move_type == 'out_invoice'
            and m.state == 'draft')
        if cash:
            if not self.env.su:
                cash._cim_check_sale_invoice_postable()
            # The accountant owns the entry when the box is ticked, or when
            # he already put a line on an account that is not an approved
            # bank: in both cases nothing is reset and nothing is matched
            # against the payment proof. Only "debits = credits" stays.
            if 'manual_journal_items' in self._fields:
                for move in cash.filtered(
                        lambda m: not self._cash_sale_is_manual(m)
                        and m._cash_sale_has_custom_account()):
                    move.manual_journal_items = True
            manual = cash.filtered(self._cash_sale_is_manual)
            (cash - manual)._cash_sale_apply_banks(strict=True)
            # receivable lines need a due date and a customer to stay open
            # for reconciliation against the customer's other invoices
            for move in cash:
                dep = move.line_ids.filtered(
                    lambda l: l.display_type != 'payment_term'
                    and l.account_id.account_type == 'asset_receivable')
                for line in dep.filtered(lambda l: not l.date_maturity):
                    line.with_context(skip_invoice_sync=True).write({
                        'date_maturity': move.invoice_date_due
                        or move.invoice_date or fields.Date.context_today(move)})
                for line in dep.filtered(lambda l: not l.partner_id):
                    line.with_context(skip_invoice_sync=True).write(
                        {'partner_id': move.partner_id.id})
        return super()._post(soft=soft)

    def _compute_amount(self):
        super()._compute_amount()
        # The bank line is not a receivable: nothing is left to collect.
        for move in self:
            if (move.x_is_cash_sale and move.state == 'posted'
                    and move.move_type == 'out_invoice'
                    and not move.line_ids.filtered(
                        lambda l: l.display_type == 'payment_term'
                        and l.account_id.account_type in (
                            'asset_receivable', 'liability_payable'))):
                # (an accountant who put the receivable line on the
                # customer's account keeps a real, open balance)
                move.amount_residual = 0.0
                move.amount_residual_signed = 0.0

    def _reverse_moves(self, default_values_list=None, cancel=False):
        if any(m.x_is_cash_sale and m.state == 'posted' for m in self):
            raise UserError(_(
                "Credit notes on a cash sale invoice are not available yet: "
                "Accounting must first decide how the refund is booked "
                "(back out of the bank or as customer credit). You can reset "
                "the invoice to draft instead."))
        return super()._reverse_moves(
            default_values_list=default_values_list, cancel=cancel)
