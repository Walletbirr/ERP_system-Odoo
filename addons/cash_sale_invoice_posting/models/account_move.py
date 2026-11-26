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

    def _cash_sale_over_under_account(self):
        """Over / under account chosen on the most recently approved payment
        proof of the cash sale order (empty if none)."""
        self.ensure_one()
        order = self.x_cash_order_id.sudo()
        proofs = order.payment_proof_ids.filtered(
            lambda p: p.state == 'approved' and p.over_under_account_id)
        if not proofs:
            return self.env['account.account']
        return proofs.sorted(
            lambda p: (p.reviewed_date or p.create_date, p.id))[-1].over_under_account_id

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
                lambda l: l.display_type == 'payment_term'
                and l.name != 'OVER/UNDER')
            if not term_lines:
                continue
            ctx = dict(skip_invoice_sync=True, dynamic_unlink=True,
                       cash_sale_sync=True)
            if not strict:
                term_lines.with_context(**ctx).write(
                    {'account_id': rows[0][0].default_account_id.id})
                stale = move.line_ids.filtered(
                    lambda l: l.display_type == 'payment_term'
                    and l.name == 'OVER/UNDER')
                if stale:
                    stale.with_context(**ctx).unlink()
                continue

            rows = move._cash_sale_bank_rows()
            currency = move.currency_id
            company_cur = move.company_id.currency_id
            total = sum(a for _j, a in rows)
            # Amount the banks received minus the invoice total: booked to the
            # over / under account chosen on the approved payment proof.
            over = currency.round(total - move.amount_total)
            has_over = not currency.is_zero(over)
            over_account = self.env['account.account']
            if has_over:
                over_account = move._cash_sale_over_under_account()
                if not over_account:
                    raise UserError(_(
                        "The approved banks (%(banks)s) differ from the "
                        "invoice total (%(total)s) by %(diff)s, but no over / "
                        "under account was chosen on the payment proof. Ask "
                        "Accounting to approve the payment proof again and "
                        "choose the account.",
                        banks=formatLang(self.env, total, currency_obj=currency),
                        total=formatLang(self.env, move.amount_total,
                                         currency_obj=currency),
                        diff=formatLang(self.env, over, currency_obj=currency)))
                if currency != company_cur:
                    raise UserError(_(
                        "An over / under on a cash sale can only be booked in "
                        "the company currency."))
            elif currency.compare_amounts(total, move.amount_total):
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
            # The bank debits add up to what the banks actually received.
            if has_over:
                # Always from the invoice total: the bank line already on the
                # draft holds the received amount, so reading it again would
                # add the difference twice.
                bank_total = company_cur.round(move.amount_total) + over
            else:
                bank_total = total_balance
            commands, used = [], 0.0
            for index, (journal, amount) in enumerate(rows):
                if index == len(rows) - 1:
                    balance = bank_total - used
                else:
                    balance = company_cur.round(bank_total * amount / total)
                    used += balance
                if has_over:
                    amount_currency = balance
                elif len(rows) > 1:
                    amount_currency = amount
                else:
                    amount_currency = total_amount
                vals = {
                    'account_id': journal.default_account_id.id,
                    'name': journal.name,
                    'balance': balance,
                    'amount_currency': amount_currency,
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
            # Re-posting: drop the over / under line of the previous posting.
            old_over = move.line_ids.filtered(
                lambda l: l.display_type == 'payment_term'
                and l.name == 'OVER/UNDER')
            if has_over:
                # Journal items only: a payment-term line like the bank
                # lines, so it stays off the Invoice Lines tab and does not
                # change the invoice total.
                commands.append(Command.create({
                    'move_id': move.id,
                    'account_id': over_account.id,
                    'name': 'OVER/UNDER',
                    'display_type': 'payment_term',
                    'partner_id': first.partner_id.id,
                    'currency_id': currency.id,
                    'balance': -over,
                    'amount_currency': -over,
                    'date_maturity': first.date_maturity,
                }))
            # Remove the extra bank lines and the previous over / under line in
            # the same write as the new lines. Unlinking them on their own
            # first leaves the entry unbalanced for a moment and fails the
            # balance check.
            for line in (term_lines - first) | old_over:
                commands.append(Command.delete(line.id))
            move.with_context(**ctx).write({'line_ids': commands})

    def _cash_sale_draft_sync(self):
        """Draft cash sale: show the bank split and the OVER/UNDER line now,
        so they can be checked before posting. Saving the draft is never
        blocked: anything not ready yet is left for posting to report."""
        for move in self:
            if not (move.x_is_cash_sale and move.move_type == 'out_invoice'
                    and move.state == 'draft'):
                continue
            rows = move._cash_sale_bank_rows()
            if not rows:
                continue
            currency = move.currency_id
            company_cur = move.company_id.currency_id
            total = sum(a for _j, a in rows)
            over = currency.round(total - move.amount_total)
            ready = all(journal.default_account_id for journal, _a in rows)
            if not currency.is_zero(over):
                ready = ready and currency == company_cur \
                    and bool(move._cash_sale_over_under_account())
            if ready:
                move._cash_sale_apply_banks(strict=True)
            else:
                move._cash_sale_apply_banks(strict=False)

    def write(self, vals):
        res = super().write(vals)
        if (not self.env.context.get('cash_sale_sync')
                and {'line_ids', 'invoice_line_ids', 'state'} & set(vals)):
            self._cash_sale_draft_sync()
        return res

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves.filtered(
            lambda m: m.x_is_cash_sale and m.move_type == 'out_invoice'
            and m.state == 'draft')._cash_sale_draft_sync()
        return moves

    def _post(self, soft=True):
        cash = self.filtered(
            lambda m: m.x_is_cash_sale and m.move_type == 'out_invoice'
            and m.state == 'draft')
        if cash:
            if not self.env.su:
                cash._cim_check_sale_invoice_postable()
            cash._cash_sale_apply_banks(strict=True)
        return super()._post(soft=soft)

    def _compute_amount(self):
        super()._compute_amount()
        # The bank line is not a receivable: nothing is left to collect.
        for move in self:
            if (move.x_is_cash_sale and move.state == 'posted'
                    and move.move_type == 'out_invoice'):
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
