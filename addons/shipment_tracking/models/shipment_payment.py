# /custom_addons/shipment_tracking/models/shipment_payment.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ShipmentCost(models.Model):
    """
    Structured per-stage cost tracking for an import shipment.

    When marked as Paid, a Journal Entry is automatically posted:
      - DEBIT  : fee_account_id  (expense / GIT account)
      - DEBIT  : tax_account_id  (if tax amount > 0)
      - CREDIT : journal_id's default account (bank/cash outflow)

    If the cost currency differs from the company currency, the user must enter
    today's exchange rate manually. The journal entry is posted using the
    manually entered rate (amount_company), not the system rate.
    """
    _name = 'shipment.cost'
    _description = 'Shipment Cost Stage'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'
    _order = 'shipment_id, stage_id'

    # ── Linked Shipment ───────────────────────────────────────────────────────
    shipment_id = fields.Many2one(
        'shipment.tracking', string='Shipment',
        required=True, ondelete='cascade', tracking=True,
    )

    # ── Stage ─────────────────────────────────────────────────────────────────
    # Configurable master-data field: users manage the list of Cost Stages
    # themselves (Costs ▸ Configuration ▸ Cost Stages) instead of being
    # limited to a fixed set of choices defined in code.
    stage_id = fields.Many2one(
        'shipment.cost.stage', string='Cost Stage',
        required=True, tracking=True, ondelete='restrict',
    )

    display_name = fields.Char(
        string='Name', compute='_compute_display_name', store=True,
    )

    # ── Payee ─────────────────────────────────────────────────────────────────
    payee_id = fields.Many2one(
        'res.partner', string='Paid To', tracking=True,
        help='Agent, authority, carrier, or government body receiving this payment.',
    )

    # ── Fee ───────────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id, tracking=True,
    )
    amount = fields.Monetary(
        string='Fee Amount', currency_field='currency_id',
        required=True, default=0.0, tracking=True,
    )

    # ── Bank Journal (shown in Fee group, right after Fee Amount) ─────────────
    journal_id = fields.Many2one(
        'account.journal', string='Bank Journal',
        domain="[('type', 'in', ['bank', 'cash'])]",
        tracking=True,
        help='Bank or Cash journal credited (money goes out) when marked as Paid.',
    )

    # ── Exchange Rate ─────────────────────────────────────────────────────────
    is_foreign_currency = fields.Boolean(
        string='Is Foreign Currency',
        compute='_compute_is_foreign_currency',
        store=True,
    )
    manual_exchange_rate = fields.Float(
        string="Today's Exchange Rate",
        digits=(16, 6),
        tracking=True,
        help=(
            "Auto-filled from Odoo's currency rates (ETB per 1 unit of the selected currency). "
            "You can override this value before saving. "
            "Used to calculate Total (Company Currency) and post the journal entry."
        ),
    )

    # ── Tax ───────────────────────────────────────────────────────────────────
    tax_amount = fields.Monetary(
        string='Tax Amount', currency_field='currency_id',
        default=0.0, tracking=True,
    )
    tax_account_id = fields.Many2one(
        'account.account', string='Tax Account',
        domain="[('account_type', 'not in', ['asset_receivable', 'liability_payable'])]",
        tracking=True,
        help='Chart of Accounts entry for the tax portion of this cost.',
    )

    # ── Total (fee + tax) ─────────────────────────────────────────────────────
    total_amount = fields.Monetary(
        string='Total (Fee + Tax)', currency_field='currency_id',
        compute='_compute_total', store=True,
    )
    amount_company = fields.Monetary(
        string='Total (Company Currency)',
        currency_field='company_currency_id',
        compute='_compute_total', store=True,
        help=(
            'Total converted to company currency using the exchange rate above. '
            'Updates live as you change Fee Amount or Exchange Rate.'
        ),
    )
    company_currency_id = fields.Many2one(
        'res.currency', string='Company Currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )

    # ── Fee Account (shown in Payment Details group) ──────────────────────────
    fee_account_id = fields.Many2one(
        'account.account', string='Fee Account',
        domain="[('account_type', 'not in', ['asset_receivable', 'liability_payable'])]",
        tracking=True,
        help='Chart of Accounts entry debited when this cost is paid (e.g. GIT account, Freight Expense).',
    )

    # ── Linked Journal Entry ──────────────────────────────────────────────────
    move_id = fields.Many2one(
        'account.move', string='Journal Entry',
        readonly=True, copy=False,
        help='Accounting journal entry created when this cost was marked as Paid.',
    )

    # ── Payment Details ───────────────────────────────────────────────────────
    due_date = fields.Date(string='Due Date', tracking=True)
    payment_date = fields.Date(string='Payment Date', tracking=True)
    payment_reference = fields.Char(
        string='Transaction / Bank Ref.', tracking=True,
        placeholder='e.g. TXN-20260506-001',
    )
    invoice_number = fields.Char(
        string='Invoice / Receipt No.', tracking=True,
        placeholder='e.g. INV-2026-0123',
    )

    # ── Status ────────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('pending',   'Pending'),
        ('paid',      'Paid'),
        ('overdue',   'Overdue'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='pending', required=True, tracking=True)

    notes = fields.Text(string='Notes')

    # ── Computed ──────────────────────────────────────────────────────────────
    @api.depends('stage_id.name', 'shipment_id.reference')
    def _compute_display_name(self):
        for rec in self:
            label = rec.stage_id.name or '?'
            ref = rec.shipment_id.reference or ''
            rec.display_name = f"{ref} — {label}" if ref else label

    @api.depends('currency_id')
    def _compute_is_foreign_currency(self):
        """
        Sets is_foreign_currency and auto-fills manual_exchange_rate from
        Odoo's currency table when a foreign currency is selected.

        Odoo stores currency.rate as: foreign units per 1 ETB (e.g. 0.006349 for USD).
        We need the inverse: ETB per 1 foreign unit (e.g. 157.50 for USD).
        """
        company_currency = self.env.company.currency_id
        for rec in self:
            is_foreign = bool(rec.currency_id) and rec.currency_id != company_currency
            rec.is_foreign_currency = is_foreign

            if is_foreign:
                rate = rec.currency_id.rate  # foreign units per 1 ETB
                if rate and rate > 0:
                    rec.manual_exchange_rate = 1.0 / rate
                # If rate is 0 or undefined, leave existing value so user can type it in
            else:
                # Reset when company currency is re-selected; field is hidden anyway
                rec.manual_exchange_rate = 0.0

    @api.onchange('currency_id')
    def _onchange_currency_id(self):
        """
        Fires immediately in the browser when the user picks a currency.
        Pre-fills Today's Exchange Rate so the user sees the live rate at once.
        The field stays fully editable — they can type a different value.
        """
        company_currency = self.env.company.currency_id
        if self.currency_id and self.currency_id != company_currency:
            rate = self.currency_id.rate  # foreign units per 1 ETB
            if rate and rate > 0:
                self.manual_exchange_rate = 1.0 / rate
            # else: leave at 0 so the warning banner prompts the user
        else:
            self.manual_exchange_rate = 0.0

    @api.depends('amount', 'tax_amount', 'currency_id', 'company_currency_id', 'manual_exchange_rate')
    def _compute_total(self):
        company = self.env.company
        today = fields.Date.today()
        for rec in self:
            rec.total_amount = (rec.amount or 0.0) + (rec.tax_amount or 0.0)
            if rec.currency_id and rec.currency_id != company.currency_id:
                # Prefer the manually entered / auto-filled rate
                if rec.manual_exchange_rate and rec.manual_exchange_rate > 0:
                    rec.amount_company = rec.total_amount * rec.manual_exchange_rate
                else:
                    # Fallback: Odoo system rate
                    rec.amount_company = rec.currency_id._convert(
                        rec.total_amount, company.currency_id, company, today,
                    )
            else:
                rec.amount_company = rec.total_amount

    # ── Status Actions ────────────────────────────────────────────────────────
    def action_mark_paid(self):
        for rec in self:
            if rec.state == 'cancelled':
                raise UserError(_('Cancelled entries cannot be marked as paid.'))
            if rec.state == 'paid':
                continue

            if not rec.fee_account_id:
                raise UserError(_(
                    'Please set a Fee Account on "%s" before marking as paid.'
                ) % rec.display_name)
            if not rec.journal_id:
                raise UserError(_(
                    'Please select a Bank Journal on "%s" before marking as paid.'
                ) % rec.display_name)
            if rec.is_foreign_currency and not rec.manual_exchange_rate:
                raise UserError(_(
                    'Please enter Today\'s Exchange Rate on "%s".\n'
                    'The fee is in a foreign currency — the exchange rate is required to post the journal entry.'
                ) % rec.display_name)
            if rec.tax_amount and not rec.tax_account_id:
                raise UserError(_(
                    'A Tax Amount is set on "%s" but no Tax Account is selected.\n'
                    'Please either select a Tax Account or set the Tax Amount to 0.'
                ) % rec.display_name)

            journal = rec.journal_id
            credit_account = (
                journal.default_account_id
                or journal.payment_credit_account_id
            )
            if not credit_account:
                raise UserError(_(
                    'Journal "%s" has no default account configured.\n'
                    'Please set a Default Account on the journal in Accounting → Configuration → Journals.'
                ) % journal.name)

            pay_date = rec.payment_date or fields.Date.today()
            company = self.env.company
            currency = rec.currency_id or company.currency_id

            if rec.is_foreign_currency and rec.manual_exchange_rate:
                fee_company    = (rec.amount or 0.0)     * rec.manual_exchange_rate
                tax_company    = (rec.tax_amount or 0.0) * rec.manual_exchange_rate
                total_company  = rec.amount_company
                entry_currency = company.currency_id
            else:
                fee_company    = rec.amount or 0.0
                tax_company    = rec.tax_amount or 0.0
                total_company  = rec.total_amount
                entry_currency = currency

            line_vals = []

            # Line 1: DEBIT the fee account
            if fee_company:
                line_vals.append((0, 0, {
                    'account_id': rec.fee_account_id.id,
                    'name': rec.display_name + (
                        ' [' + rec.invoice_number + ']' if rec.invoice_number else ''
                    ),
                    'partner_id': rec.payee_id.id if rec.payee_id else False,
                    'debit':  fee_company,
                    'credit': 0.0,
                    'currency_id': entry_currency.id,
                }))

            # Line 2: DEBIT the tax account (if tax > 0)
            if tax_company and rec.tax_account_id:
                line_vals.append((0, 0, {
                    'account_id': rec.tax_account_id.id,
                    'name': rec.display_name + ' — Tax',
                    'partner_id': rec.payee_id.id if rec.payee_id else False,
                    'debit':  tax_company,
                    'credit': 0.0,
                    'currency_id': entry_currency.id,
                }))

            # Line 3: CREDIT the bank/cash account
            # Use the actual sum of debit lines to guarantee the entry is balanced.
            total_debit = sum(
                vals[2]['debit'] for vals in line_vals if vals[2].get('debit')
            )
            line_vals.append((0, 0, {
                'account_id': credit_account.id,
                'name': rec.display_name + ' — Payment',
                'partner_id': rec.payee_id.id if rec.payee_id else False,
                'debit':  0.0,
                'credit': total_debit,
                'currency_id': entry_currency.id,
            }))

            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': pay_date,
                'ref': '%s — %s' % (rec.shipment_id.reference or '', rec.display_name),
                'line_ids': line_vals,
            })
            move.action_post()

            rec.write({
                'state':        'paid',
                'payment_date': pay_date,
                'move_id':      move.id,
            })

    def action_mark_pending(self):
        for rec in self:
            if rec.state == 'paid':
                raise UserError(_('Paid entries cannot be reset to pending.'))
            rec.state = 'pending'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'paid':
                raise UserError(_('Paid entries cannot be cancelled.'))
            rec.state = 'cancelled'

    def action_view_journal_entry(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No journal entry linked to this cost record.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }

    # ── Cron: auto-mark overdue ───────────────────────────────────────────────
    @api.model
    def _cron_update_overdue(self):
        today = fields.Date.today()
        overdue = self.search([
            ('state', '=', 'pending'),
            ('due_date', '<', today),
            ('due_date', '!=', False),
        ])
        overdue.write({'state': 'overdue'})

    # ── Prevent deletion of paid records ──────────────────────────────────────
    def unlink(self):
        for rec in self:
            if rec.state == 'paid':
                raise UserError(_(
                    'Cannot delete "%s" because it is already paid.\n'
                    'Cancel the entry first if you need to remove it.'
                ) % rec.display_name)
        return super().unlink()
