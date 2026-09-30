# -*- coding: utf-8 -*-
import calendar
import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Odoo 18 account_type values that make up the Profit & Loss report.
PL_ACCOUNT_TYPES = (
    'income', 'income_other',
    'expense', 'expense_depreciation', 'expense_direct_cost',
)

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
    ], default='year', required=True,
        help="Fiscal Year: pick a year and the dates below are filled in for "
             "you (the whole fiscal year). Custom Range: type Date From / "
             "Date To yourself.")
    fiscal_year = fields.Selection(
        selection='_selection_fiscal_years', string='Fiscal Year',
        help="The year the fiscal year ENDS in (for a January-December "
             "fiscal year that is simply the calendar year).")
    # Server-computed from the picked year, but still editable for Custom
    # Range. Being stored+computed means the dates are always derived on the
    # server whenever the year changes - they no longer depend on the browser
    # sending them back (read-only fields are not saved by the web client).
    date_from = fields.Date(
        compute='_compute_period_dates', store=True, readonly=False,
        precompute=True, required=True)
    date_to = fields.Date(
        compute='_compute_period_dates', store=True, readonly=False,
        precompute=True, required=True)
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
        """Every year from the earliest posted entry in the database (and at
        least 10 years back) up to 20 years ahead, newest first."""
        this_year = fields.Date.context_today(self).year
        first_move = self.env['account.move'].sudo().search(
            [('state', '=', 'posted')], order='date asc', limit=1)
        first_year = first_move.date.year if first_move else this_year
        start = min(first_year, this_year - 10)
        return [(str(y), str(y)) for y in range(this_year + 20, start - 1, -1)]

    @api.model
    def _fiscal_year_dates(self, company, year):
        """(date_from, date_to) of the fiscal year that ENDS in calendar
        `year`, using the company's own fiscal year end (Dec 31 by default)."""
        last_month = int(company.fiscalyear_last_month or 12)
        last_day = min(company.fiscalyear_last_day or 31,
                       calendar.monthrange(year, last_month)[1])
        fy = company.compute_fiscalyear_dates(date(year, last_month, last_day))
        return fy['date_from'], fy['date_to']

    @api.model
    def _get_prior_fiscalyear_dates(self, company):
        """The most recently COMPLETED fiscal year as of today, for company."""
        today = fields.Date.context_today(self)
        current_dates = company.compute_fiscalyear_dates(today)
        prior_reference = current_dates['date_from'] - relativedelta(days=1)
        return company.compute_fiscalyear_dates(prior_reference)

    @api.depends('period_type', 'fiscal_year', 'company_id')
    def _compute_period_dates(self):
        for rec in self:
            if rec.period_type == 'year' and rec.fiscal_year:
                company = rec.company_id or self.env.company
                rec.date_from, rec.date_to = self._fiscal_year_dates(
                    company, int(rec.fiscal_year))
            else:
                # Custom Range: keep exactly what was typed in.
                rec.date_from = rec.date_from
                rec.date_to = rec.date_to

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env['res.company'].browse(res.get('company_id')).exists() or self.env.company

        if 'journal_id' in fields_list and not res.get('journal_id'):
            res['journal_id'] = company.closing_journal_id.id
        if 'retained_earnings_account_id' in fields_list and not res.get('retained_earnings_account_id'):
            res['retained_earnings_account_id'] = company.retained_earnings_account_id.id
        # Only the year is defaulted (the most recently completed fiscal
        # year); date_from/date_to are then derived from it by
        # _compute_period_dates, so the two can never disagree.
        if 'fiscal_year' in fields_list and not res.get('fiscal_year'):
            prior_dates = self._get_prior_fiscalyear_dates(company)
            res['fiscal_year'] = str(prior_dates['date_to'].year)
        return res

    @api.onchange('company_id')
    def _onchange_company_id(self):
        for rec in self:
            rec.journal_id = rec.company_id.closing_journal_id
            rec.retained_earnings_account_id = rec.company_id.retained_earnings_account_id

    @api.model
    def _repair_stale_periods(self):
        """Runs on upgrade. Draft/Computed records saved by an older build
        can show one Fiscal Year while still storing the dates of another
        (the old form never saved the auto-filled dates). Re-derive their
        dates from the year; a record that had already been computed is put
        back to Draft because its balances belonged to the wrong period."""
        stale = self.sudo().search([
            ('period_type', '=', 'year'), ('fiscal_year', '!=', False),
            ('state', 'in', ('draft', 'computed'))])
        for rec in stale:
            date_from, date_to = self._fiscal_year_dates(rec.company_id, int(rec.fiscal_year))
            if (rec.date_from, rec.date_to) == (date_from, date_to):
                continue
            try:
                with self.env.cr.savepoint():
                    rec.line_ids.unlink()
                    rec.write({'date_from': date_from, 'date_to': date_to, 'state': 'draft'})
            except Exception:  # e.g. another closing already owns that period
                _logger.warning("Could not realign closing %s to fiscal year %s", rec.id, rec.fiscal_year)

    @api.model
    def _place_menus(self):
        """Nest our two menus inside the Accounting app's real Configuration /
        Accounting submenus. Called from menu_views.xml, so it runs on every
        install AND upgrade (a post_init_hook only runs on a fresh install,
        while every upgrade re-loads the XML and resets the parent to the
        app root). Submenus are found by name under the Accounting app root,
        so no xmlid has to be guessed; if one isn't found the menu simply
        stays directly under the app root."""
        Menu = self.env['ir.ui.menu'].sudo()
        root = self.env.ref('account.menu_finance', raise_if_not_found=False)
        setup_menu = self.env.ref(
            'automatic_retained_earnings.menu_retained_earnings_config', raise_if_not_found=False)
        closing_menu = self.env.ref(
            'automatic_retained_earnings.menu_account_fiscalyear_closing', raise_if_not_found=False)
        if not root:
            return

        def find(label):
            candidates = Menu.search([
                ('id', 'child_of', root.id), ('id', '!=', root.id),
                ('name', '=ilike', label)])
            if not candidates:
                return Menu.browse()

            def depth(menu):
                d, cur = 0, menu
                while cur.parent_id and cur.id != root.id and d < 20:
                    cur, d = cur.parent_id, d + 1
                return d
            return Menu.browse(min(candidates, key=depth).id)

        config_menu, accounting_menu = find('Configuration'), find('Accounting')
        if setup_menu and config_menu:
            setup_menu.sudo().write({'parent_id': config_menu.id, 'sequence': 99})
        if closing_menu and accounting_menu:
            closing_menu.sudo().write({'parent_id': accounting_menu.id, 'sequence': 99})

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

    def action_compute_lines(self):
        self.ensure_one()
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
        # Dated the SAME day as the closing so the period is genuinely
        # re-opened (a reversal dated later would push the old year's P&L
        # into the current year). Flagged like the closing itself, so both
        # are ignored when the period is computed again.
        reversal = self.move_id._reverse_moves(default_values_list=[{
            'date': self.date_to,
            'ref': _('Reversal of %s') % self.move_id.name,
        }], cancel=False)
        reversal.write({'fiscalyear_closing_id': self.id})
        reversal.action_post()
        self.write({'state': 'reversed', 'reversal_move_id': reversal.id})
        return True

    def action_reset_to_draft(self):
        self.ensure_one()
        if self.state == 'posted':
            raise UserError(_('Reverse the posted entry before resetting to draft.'))
        # From "Reversed" this is the way to redo a period (only one closing
        # record can exist per company and period). The old closing and its
        # reversal stay in the ledger as the audit trail.
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
