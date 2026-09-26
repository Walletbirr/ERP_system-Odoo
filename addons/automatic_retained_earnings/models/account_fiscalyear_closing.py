# -*- coding: utf-8 -*-
import calendar

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

# Odoo 18 account_type values that make up the Profit & Loss report.
PL_ACCOUNT_TYPES = (
    'income', 'income_other',
    'expense', 'expense_depreciation', 'expense_direct_cost',
)

MONTH_SELECTION = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
    ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
    ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December'),
]


class AccountFiscalyearClosing(models.Model):
    _name = 'account.fiscalyear.closing'
    _description = 'Retained Earnings Fiscal Year Closing'
    _order = 'date_to desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    period_type = fields.Selection([
        ('year', 'Fiscal Year'),
        ('custom', 'Custom Range'),
    ], default='year', required=True, tracking=True,
        help="Pick a Fiscal Year (optionally narrowed to one month) and the "
             "dates below fill in automatically, or switch to Custom Range "
             "to set Date From/To by hand.")
    fiscal_year = fields.Selection(
        selection='_selection_fiscal_years', string='Fiscal Year')
    period_month = fields.Selection(
        MONTH_SELECTION, string='Month',
        help="Leave empty to close the full fiscal year. Pick a month to "
             "close just that month instead (e.g. to close September only).")
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    journal_id = fields.Many2one(
        'account.journal', required=True, string='Closing Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]")
    retained_earnings_account_id = fields.Many2one(
        'account.account', required=True, string='Retained Earnings Account',
        domain="[('account_type', '=', 'equity')]")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('computed', 'Computed'),
        ('posted', 'Posted'),
        ('reversed', 'Reversed'),
    ], default='draft', required=True, copy=False, tracking=True)
    move_id = fields.Many2one('account.move', readonly=True, copy=False)
    reversal_move_id = fields.Many2one('account.move', readonly=True, copy=False)
    line_ids = fields.One2many(
        'account.fiscalyear.closing.line', 'closing_id', string='Account Balances')
    total_income = fields.Monetary(compute='_compute_totals', store=True)
    total_expense = fields.Monetary(compute='_compute_totals', store=True)
    net_result = fields.Monetary(
        compute='_compute_totals', store=True,
        help="Positive = net profit for the period, Negative = net loss.")
    auto_generated = fields.Boolean(default=False, readonly=True,
                                     help="Created automatically by the scheduled action.")

    _sql_constraints = [
        ('period_company_uniq', 'unique(company_id, date_from, date_to)',
         'A Fiscal Year Closing already exists for this company and period.'),
    ]

    @api.depends('date_to')
    def _compute_name(self):
        for rec in self:
            rec.name = _('Retained Earnings Closing - %s') % (rec.date_to.year if rec.date_to else '...')

    @api.depends('line_ids.balance', 'line_ids.account_id.account_type')
    def _compute_totals(self):
        for rec in self:
            income = sum(
                l.balance for l in rec.line_ids
                if l.account_id.account_type in ('income', 'income_other'))
            expense = sum(
                l.balance for l in rec.line_ids
                if l.account_id.account_type in
                ('expense', 'expense_depreciation', 'expense_direct_cost'))
            # income accounts are naturally credit-balance -> negative "balance" (debit - credit)
            rec.total_income = -income
            rec.total_expense = expense
            rec.net_result = -income - expense

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('The start date must be before the end date.'))

    @api.model
    def _selection_fiscal_years(self):
        """Recent + upcoming years, newest first, for the Fiscal Year picker."""
        current_year = fields.Date.context_today(self).year
        return [(str(y), str(y)) for y in range(current_year + 1, current_year - 7, -1)]

    @api.model
    def _get_prior_fiscalyear_dates(self, company):
        """The most recently COMPLETED fiscal year as of today, for company."""
        today = fields.Date.context_today(self)
        current_dates = company.compute_fiscalyear_dates(today)
        prior_reference = current_dates['date_from'] - relativedelta(days=1)
        return company.compute_fiscalyear_dates(prior_reference)

    def _dates_for_fiscal_year(self, year, month=None):
        """Date range for a picked (Fiscal Year, optional Month), scoped to
        company_id's actual fiscal year window (handles non-calendar fiscal
        years, e.g. one starting in July)."""
        self.ensure_one()
        company = self.company_id or self.env.company
        fy_dates = company.compute_fiscalyear_dates(fields.Date.to_date('%s-12-31' % year))
        date_from, date_to = fy_dates['date_from'], fy_dates['date_to']
        if month:
            month = int(month)
            last_day = calendar.monthrange(year, month)[1]
            month_from = fields.Date.to_date('%04d-%02d-01' % (year, month))
            month_to = fields.Date.to_date('%04d-%02d-%02d' % (year, month, last_day))
            # clip to the fiscal year window in case the month falls just
            # outside it (e.g. fiscal year not aligned to the calendar year)
            date_from = max(date_from, month_from)
            date_to = min(date_to, month_to)
        return date_from, date_to

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env['res.company'].browse(res.get('company_id')).exists() or self.env.company

        if 'journal_id' in fields_list and not res.get('journal_id'):
            res['journal_id'] = company.closing_journal_id.id
        if 'retained_earnings_account_id' in fields_list and not res.get('retained_earnings_account_id'):
            res['retained_earnings_account_id'] = company.retained_earnings_account_id.id

        needs_period = {'date_from', 'date_to', 'fiscal_year'} & set(fields_list)
        if needs_period and res.get('period_type', 'year') == 'year':
            prior_dates = self._get_prior_fiscalyear_dates(company)
            res.setdefault('date_from', prior_dates['date_from'])
            res.setdefault('date_to', prior_dates['date_to'])
            res.setdefault('fiscal_year', str(prior_dates['date_to'].year))
        return res

    @api.onchange('company_id')
    def _onchange_company_id(self):
        for rec in self:
            rec.journal_id = rec.company_id.closing_journal_id
            rec.retained_earnings_account_id = rec.company_id.retained_earnings_account_id
            if rec.period_type == 'year' and rec.fiscal_year:
                date_from, date_to = rec._dates_for_fiscal_year(
                    int(rec.fiscal_year), rec.period_month)
                rec.date_from, rec.date_to = date_from, date_to

    @api.onchange('period_type', 'fiscal_year', 'period_month')
    def _onchange_period_selection(self):
        for rec in self:
            if rec.period_type != 'year' or not rec.fiscal_year:
                continue
            date_from, date_to = rec._dates_for_fiscal_year(
                int(rec.fiscal_year), rec.period_month)
            rec.date_from, rec.date_to = date_from, date_to

    def _get_pl_move_lines(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', 'in', PL_ACCOUNT_TYPES),
            ('account_id.deprecated', '=', False),
            # Exclude any previous closing entries so re-running a closing
            # (after a reversal) never re-closes an already-closed period.
            ('move_id.fiscalyear_closing_id', '=', False),
        ]
        return self.env['account.move.line'].search(domain)

    def _sync_dates_from_period(self):
        """Server-side source of truth for the period. Whenever period_type
        is 'year', derive date_from/date_to from Fiscal Year (+ optional
        Month) right before they're used, instead of trusting whatever is
        already stored on the record - so a period picked in the form
        always wins, even if the client-side onchange never made it into
        the saved values. Custom Range periods are left exactly as entered.
        """
        for rec in self:
            if rec.period_type != 'year' or not rec.fiscal_year:
                continue
            date_from, date_to = rec._dates_for_fiscal_year(
                int(rec.fiscal_year), rec.period_month)
            if rec.date_from != date_from or rec.date_to != date_to:
                rec.write({'date_from': date_from, 'date_to': date_to})

    def action_compute_lines(self):
        self.ensure_one()
        self._sync_dates_from_period()
        if self.state == 'posted':
            raise UserError(_('This closing has already been posted. Reverse it first to recompute.'))

        move_lines = self._get_pl_move_lines()
        totals = {}
        for ml in move_lines:
            totals[ml.account_id] = totals.get(ml.account_id, 0.0) + ml.balance

        self.line_ids.unlink()
        vals = []
        for account, balance in totals.items():
            if self.company_id.currency_id.is_zero(balance):
                continue
            vals.append((0, 0, {'account_id': account.id, 'balance': balance}))

        if not vals:
            raise UserError(_(
                'No posted Income or Expense entries were found between %s and %s.'
            ) % (self.date_from, self.date_to))

        self.write({'line_ids': vals, 'state': 'computed'})
        return True

    def action_post(self):
        self.ensure_one()
        self._sync_dates_from_period()
        if self.state == 'posted':
            raise UserError(_('This closing has already been posted.'))
        if not self.line_ids:
            self.action_compute_lines()
        if not self.retained_earnings_account_id:
            raise UserError(_('Please set a Retained Earnings account before posting.'))

        move_line_vals = []
        running_total = 0.0
        for line in self.line_ids:
            closing_balance = -line.balance  # the reversing entry that zeroes the account
            if self.company_id.currency_id.is_zero(closing_balance):
                continue
            running_total += closing_balance
            move_line_vals.append((0, 0, {
                'account_id': line.account_id.id,
                'name': _('Closing %s - FY %s') % (line.account_id.display_name, self.date_to.year),
                'debit': closing_balance if closing_balance > 0 else 0.0,
                'credit': -closing_balance if closing_balance < 0 else 0.0,
            }))

        # Balancing line: whatever is left nets the whole entry to zero and
        # lands the year's net profit/loss on the Retained Earnings account.
        retained_balance = -running_total
        move_line_vals.append((0, 0, {
            'account_id': self.retained_earnings_account_id.id,
            'name': _('Retained Earnings - FY %s') % self.date_to.year,
            'debit': retained_balance if retained_balance > 0 else 0.0,
            'credit': -retained_balance if retained_balance < 0 else 0.0,
        }))

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'date': self.date_to,
            'ref': _('Retained Earnings Closing FY %s') % self.date_to.year,
            'fiscalyear_closing_id': self.id,
            'line_ids': move_line_vals,
        })
        move.action_post()
        self.write({'move_id': move.id, 'state': 'posted'})
        return True

    def action_reverse(self):
        self.ensure_one()
        if self.state != 'posted' or not self.move_id:
            raise UserError(_('Only a posted closing can be reversed.'))
        today = fields.Date.context_today(self)
        reversal = self.move_id._reverse_moves(default_values_list=[{
            'date': max(self.date_to, today),
            'ref': _('Reversal of %s') % self.move_id.name,
        }], cancel=False)
        reversal.action_post()
        self.write({'state': 'reversed', 'reversal_move_id': reversal.id})
        return True

    def action_reset_to_draft(self):
        self.ensure_one()
        if self.state == 'posted':
            raise UserError(_('Reverse the posted entry before resetting to draft.'))
        if self.state == 'reversed':
            raise UserError(_(
                'This closing was already posted and reversed, so its record is '
                'part of the audit trail. Create a new Fiscal Year Closing for '
                'this period instead of resetting this one.'))
        self.line_ids.unlink()
        self.write({
            'state': 'draft',
            'move_id': False,
            'reversal_move_id': False,
        })
        return True

    def action_view_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Closing Entry'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    @api.model
    def _cron_auto_close_fiscalyear(self):
        import calendar

        companies = self.env['res.company'].sudo().search([('auto_close_fiscalyear', '=', True)])
        today = fields.Date.context_today(self)
        for company in companies:
            if not company.retained_earnings_account_id:
                continue
            if not company.auto_close_month or not company.auto_close_day:
                continue

            # Only fire on the one configured calendar day each year.
            month = int(company.auto_close_month)
            last_day_of_month = calendar.monthrange(today.year, month)[1]
            trigger_day = min(company.auto_close_day, last_day_of_month)
            if not (today.month == month and today.day == trigger_day):
                continue

            # Find the most recently COMPLETED fiscal year as of today,
            # regardless of how long ago it ended (supports a grace period:
            # Auto-Post Date can be weeks/months after the fiscal year end).
            current_dates = company.compute_fiscalyear_dates(today)
            prior_reference = current_dates['date_from'] - relativedelta(days=1)
            prior_dates = company.compute_fiscalyear_dates(prior_reference)
            date_from, date_to = prior_dates['date_from'], prior_dates['date_to']
            if today <= date_to:
                continue  # safety guard, should not happen

            existing = self.sudo().search([
                ('company_id', '=', company.id),
                ('date_from', '=', date_from),
                ('date_to', '=', date_to),
            ], limit=1)
            if existing:
                continue

            journal = company.closing_journal_id or self.env['account.journal'].sudo().search(
                [('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
            if not journal:
                continue

            closing = self.sudo().create({
                'company_id': company.id,
                'date_from': date_from,
                'date_to': date_to,
                'journal_id': journal.id,
                'retained_earnings_account_id': company.retained_earnings_account_id.id,
                'auto_generated': True,
            })
            try:
                closing.action_compute_lines()
                closing.action_post()
            except UserError:
                # nothing to close (e.g. zero activity) or another blocking
                # condition - leave the draft record for manual review
                continue


class AccountFiscalyearClosingLine(models.Model):
    _name = 'account.fiscalyear.closing.line'
    _description = 'Retained Earnings Closing Line (pre-closing account balance)'

    closing_id = fields.Many2one(
        'account.fiscalyear.closing', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', required=True, readonly=True)
    account_type = fields.Selection(related='account_id.account_type')
    currency_id = fields.Many2one(related='closing_id.currency_id')
    balance = fields.Monetary(
        readonly=True,
        help="Account balance (debit - credit) for the period, before closing.")
