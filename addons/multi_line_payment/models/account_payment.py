# -*- coding: utf-8 -*-
from lxml import etree

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # Accounting voucher names: Send = CPV, Receive = CRV
    payment_type = fields.Selection(
        selection=[
            ('outbound', 'Cash Payment Voucher (CPV)'),
            ('inbound', 'Cash Receipt Voucher (CRV)'),
        ])

    voucher_reference = fields.Char(
        string="Reference", copy=False,
        help="The only source of the journal entry Reference (Purpose is not used). "
             "Cannot be changed after posting.")
    tax_amount = fields.Monetary(
        string="Tax / VAT", currency_field='currency_id',
        compute='_compute_tax_amount',
        help="Positive tax / VAT lines of the payment. Posted on the entry but "
             "not part of the Amount.")
    is_multi_line = fields.Boolean(string="Multiple Lines", copy=True)
    multi_line_ids = fields.One2many(
        'account.payment.multi.line', 'payment_id',
        string="Payment Lines", copy=True)

    # -------------------------------------------------------------------------
    # AMOUNT = EXPENSES ONLY (positive lines, tax / VAT lines left out)
    # The bank / cash line of the journal entry carries only the NET total
    # (positive lines minus negative lines), so the entry always balances.
    # -------------------------------------------------------------------------

    def _get_multi_line_totals(self):
        """ Return (total, net): total = sum of the positive lines that are not
        tax / VAT lines (shown as the payment Amount, i.e. the expenses only),
        net = sum of ALL lines (posted on the bank line so the entry balances). """
        self.ensure_one()
        lines = self.multi_line_ids
        total = sum(l.amount for l in lines if l.amount > 0 and not l.is_tax)
        net = sum(lines.mapped('amount'))
        return total, net

    @api.depends('multi_line_ids.amount', 'multi_line_ids.account_id', 'is_multi_line')
    def _compute_tax_amount(self):
        for pay in self:
            pay.tax_amount = sum(
                l.amount for l in pay.multi_line_ids if l.amount > 0 and l.is_tax
            ) if pay.is_multi_line else 0.0

    @api.onchange('multi_line_ids', 'is_multi_line')
    def _onchange_multi_line_ids(self):
        for pay in self:
            if pay.is_multi_line:
                pay.amount = pay._get_multi_line_totals()[0]

    @api.constrains('is_multi_line', 'multi_line_ids')
    def _check_multi_line_has_positive(self):
        """ Lines may be negative (opposite side) and the net may be negative
        too: the bank line then simply goes on the other side. The payment
        Amount (total of the positive lines) must still be above zero. """
        for pay in self.filtered(lambda p: p.is_multi_line and p.multi_line_ids):
            total = pay._get_multi_line_totals()[0]
            if pay.currency_id.compare_amounts(total, 0.0) <= 0:
                raise ValidationError(_(
                    "Add at least one expense line with a positive amount (tax lines do not count)."))

    def _sync_multi_line_amount(self):
        """ The amount field is read-only in the form (so the browser does not
        send it back): always rebuild it from the lines on the server. """
        for pay in self.filtered('is_multi_line'):
            total = pay._get_multi_line_totals()[0]
            if pay.currency_id.compare_amounts(pay.amount, total) != 0:
                pay.with_context(skip_multi_line_amount_sync=True).write({'amount': total})

    # -------------------------------------------------------------------------
    # READ-ONLY AFTER POSTING
    # -------------------------------------------------------------------------

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """ Every field of the payment form becomes read-only once the payment
        is no longer a draft (Reset To Draft unlocks it again). """
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form' and arch.xpath("//field[@name='state']"):
            for node in arch.xpath("//sheet//field[not(ancestor::field)]"):
                _make_readonly_when(node, "state != 'draft'")
        return arch, view

    # -------------------------------------------------------------------------
    # REFERENCE -> JOURNAL ENTRY
    # -------------------------------------------------------------------------

    def _push_reference_to_move(self):
        """ The journal entry Reference comes from the payment Reference only
        (never from Purpose / memo): an empty Reference leaves it empty. """
        for pay in self:
            move = pay.move_id
            target = pay.voucher_reference or False
            if move and (move.ref or False) != target:
                move.with_context(allow_payment_move_ref_write=True).write(
                    {'ref': target})

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        payments._sync_multi_line_amount()
        return payments

    def write(self, vals):
        if 'voucher_reference' in vals and any(p.state != 'draft' for p in self):
            raise UserError(_(
                "The reference cannot be changed after the payment is posted. "
                "Reset the payment to draft first."))
        res = super().write(vals)
        if (
            not self.env.context.get('skip_multi_line_amount_sync')
            and ('multi_line_ids' in vals or 'is_multi_line' in vals)
        ):
            self._sync_multi_line_amount()
        return res

    # -------------------------------------------------------------------------
    # JOURNAL ENTRY LINES
    # -------------------------------------------------------------------------

    def _prepare_multi_line_vals(self):
        """ One journal item per payment line.

        Payment Voucher (send):  positive line = debit,  negative line = credit.
        Receipt Voucher (receive): positive line = credit, negative line = debit.
        The bank line of the journal is added by Odoo for the net amount. """
        self.ensure_one()
        sign = 1 if self.payment_type == 'outbound' else -1
        company = self.company_id
        date = self.date or fields.Date.context_today(self)
        vals_list = []
        for line in self.multi_line_ids:
            amount_currency = sign * line.amount
            balance = self.currency_id._convert(
                amount_currency, company.currency_id, company, date)
            vals_list.append({
                'name': line.name or False,
                'date_maturity': date,
                'amount_currency': amount_currency,
                'currency_id': self.currency_id.id,
                'balance': balance,
                'partner_id': (line.partner_id or self.partner_id).id,
                'account_id': line.account_id.id,
            })
        return vals_list

    def _prepare_move_lines_per_type(self, write_off_line_vals=None, force_balance=None):
        res = super()._prepare_move_lines_per_type(
            write_off_line_vals=write_off_line_vals, force_balance=force_balance)
        self.ensure_one()
        if self.is_multi_line and self.multi_line_ids:
            # Bank side: always the bank / cash account set on the journal.
            bank_account = self.journal_id.default_account_id
            if not bank_account:
                raise UserError(_(
                    "The journal %s has no default account. Set the bank account "
                    "on the journal first.", self.journal_id.display_name))
            # The payment Amount is the total of the lines, but the bank line
            # only carries the net (positive minus negative lines).
            net = self._get_multi_line_totals()[1]
            sign = -1 if self.payment_type == 'outbound' else 1
            amount_currency = sign * net
            balance = self.currency_id._convert(
                amount_currency, self.company_id.currency_id,
                self.company_id, self.date or fields.Date.context_today(self))
            for liquidity_vals in res.get('liquidity_lines', []):
                liquidity_vals['account_id'] = bank_account.id
                liquidity_vals['amount_currency'] = amount_currency
                liquidity_vals.pop('debit', None)
                liquidity_vals.pop('credit', None)
                liquidity_vals['balance'] = balance
            res['counterpart_lines'] = self._prepare_multi_line_vals()
            res['write_off_lines'] = []
        return res

    # -------------------------------------------------------------------------
    # SYNCHRONIZATION WITH THE JOURNAL ENTRY
    # -------------------------------------------------------------------------

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        return super()._get_trigger_fields_to_synchronize() + (
            'is_multi_line', 'multi_line_ids')

    def _synchronize_to_moves(self, changed_fields):
        multi = self.filtered(lambda p: p.is_multi_line and p.multi_line_ids)
        super(AccountPayment, self - multi)._synchronize_to_moves(changed_fields)
        if not multi:
            return
        if not any(f in changed_fields for f in self._get_trigger_fields_to_synchronize()):
            return
        for pay in multi:
            # No entry yet (draft): it is generated on Confirm.
            if not pay.move_id or pay.move_id.state == 'posted':
                continue
            line_vals = pay._prepare_move_line_default_vals()
            to_write = {
                'date': pay.date,
                'partner_id': pay.partner_id.id,
                'currency_id': pay.currency_id.id,
                'partner_bank_id': pay.partner_bank_id.id,
                'line_ids': [Command.clear()] + [Command.create(v) for v in line_vals],
            }
            if 'journal_id' in changed_fields:
                to_write.update({'name': '/', 'journal_id': pay.journal_id.id})
            pay.move_id.with_context(skip_invoice_sync=True).write(to_write)

    def _synchronize_from_moves(self, changed_fields):
        multi = self.filtered(lambda p: p.is_multi_line and p.multi_line_ids)
        return super(AccountPayment, self - multi)._synchronize_from_moves(changed_fields)

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def action_preview_post(self):
        """ Confirm button of every payment: open a confirmation window
        listing the debits and credits that will be posted. Nothing is posted
        until the user clicks "Confirm and Post" in that window. """
        self.ensure_one()
        if self.is_multi_line:
            if not self.multi_line_ids:
                raise UserError(_("Add at least one payment line before confirming."))
            self._sync_multi_line_amount()

        entries = []
        for vals in self._prepare_move_line_default_vals():
            balance = vals.get('balance')
            if balance is None:
                balance = vals.get('debit', 0.0) - vals.get('credit', 0.0)
            entries.append((vals, balance))
        # Debits first, then credits.
        entries.sort(key=lambda e: e[1] < 0)

        company_currency = self.company_id.currency_id
        lines = [
            Command.create({
                'sequence': seq,
                'company_currency_id': company_currency.id,
                'account_id': vals.get('account_id'),
                'partner_id': vals.get('partner_id'),
                'name': vals.get('name') or False,
                'debit': balance if balance > 0 else 0.0,
                'credit': -balance if balance < 0 else 0.0,
            })
            for seq, (vals, balance) in enumerate(entries)
        ]
        preview = self.env['account.payment.post.preview'].create({
            'payment_id': self.id,
            'line_ids': lines,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _("Confirm Journal Entry"),
            'res_model': 'account.payment.post.preview',
            'res_id': preview.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_post(self):
        for pay in self.filtered('is_multi_line'):
            if not pay.multi_line_ids:
                raise UserError(_("Add at least one payment line before confirming."))
            pay._sync_multi_line_amount()
        # Reference typed on the payment goes on the journal entry.
        self.filtered(lambda p: p.move_id.state == 'draft')._push_reference_to_move()
        res = super().action_post()
        self._push_reference_to_move()
        return res


def _make_readonly_when(node, condition):
    """ Add `condition` to the readonly attribute of a view node. """
    current = (node.get('readonly') or '').strip()
    if current in ('1', 'True', 'true'):
        return
    if current and current not in ('0', 'False', 'false'):
        node.set('readonly', "(%s) or (%s)" % (current, condition))
    else:
        node.set('readonly', condition)


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """ A posted journal entry created by a payment is fully read-only. """
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form' and arch.xpath("//field[@name='state']"):
            sheets = arch.xpath("//sheet")
            if sheets:
                if not arch.xpath("//field[@name='origin_payment_id']"):
                    sheets[0].insert(0, etree.Element(
                        'field', name='origin_payment_id', invisible='1'))
                for node in arch.xpath("//sheet//field[not(ancestor::field)]"):
                    if node.get('name') == 'origin_payment_id':
                        continue
                    _make_readonly_when(node, "state != 'draft' and origin_payment_id")
        return arch, view

    def write(self, vals):
        if 'ref' in vals and not self.env.context.get('allow_payment_move_ref_write'):
            for move in self:
                if (
                    move.state == 'posted' and move.origin_payment_id
                    and (move.ref or '') != (vals['ref'] or '')
                ):
                    raise UserError(_(
                        "The reference of a posted payment entry cannot be changed."))
        return super().write(vals)
