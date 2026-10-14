# -*- coding: utf-8 -*-
import math

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round


class HrLoan(models.Model):
    _name = 'hr.loan'
    _description = 'Employee Loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------
    def _default_first_deduction_date(self):
        return (fields.Date.context_today(self) + relativedelta(months=1)).replace(day=1)

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------
    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True, readonly=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True,
        tracking=True, check_company=True,
        domain=[('contract_ids.state', '=', 'open')],
        help="Only employees with a running contract are listed.")
    date = fields.Date(
        string='Loan Date', required=True, tracking=True,
        default=fields.Date.context_today)
    loan_amount = fields.Monetary(
        string='Loan Amount', required=True, tracking=True,
        currency_field='currency_id')
    installment_amount = fields.Monetary(
        string='Monthly Installment', required=True, tracking=True,
        currency_field='currency_id',
        help="Fixed amount deducted every month. The last installment is "
             "automatically smaller if the loan does not divide evenly.")
    installment_count = fields.Integer(
        string='Number of Installments', compute='_compute_installment_count', store=True)
    first_deduction_date = fields.Date(
        string='First Deduction', required=True, tracking=True,
        default=_default_first_deduction_date,
        help="Month of the first installment. Later installments follow monthly.")
    note = fields.Text(string='Notes / Agreement Terms')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('paid', 'Fully Paid'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, copy=False,
        tracking=True, index=True)

    # Deduction control ------------------------------------------------
    deduction_active = fields.Boolean(
        string='Deduction Active', default=True, tracking=True, copy=False,
        help="Untick (or use Pause Deduction) to stop deducting this loan "
             "from payroll until you resume it.")
    pause_reason = fields.Char(string='Pause Reason', tracking=True)
    company_deduction_paused = fields.Boolean(
        related='company_id.loan_deduction_paused')
    company_deduction_pause_reason = fields.Char(
        related='company_id.loan_deduction_pause_reason')
    deduction_status = fields.Selection([
        ('na', '-'),
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('global_hold', 'On Hold (All Loans)'),
    ], string='Deduction', compute='_compute_deduction_status')

    pause_log_ids = fields.One2many('hr.loan.pause.log', 'loan_id', string='Pause History')

    # Accounting -------------------------------------------------------
    create_disbursement_entry = fields.Boolean(
        string='Post Disbursement Entry', default=True,
        help="Untick for loans that were already paid out before using this "
             "module (no journal entry is created).")
    journal_id = fields.Many2one(
        'account.journal', string='Disbursement Journal', check_company=True,
        domain="[('type', 'in', ('bank', 'cash', 'general'))]",
        default=lambda self: self.env.company.loan_journal_id)
    loan_account_id = fields.Many2one(
        'account.account', string='Loan Receivable Account',
        domain="[('account_type', 'in', ('asset_current', 'asset_receivable', 'asset_non_current'))]",
        default=lambda self: self.env.company.loan_account_id)
    disbursement_account_id = fields.Many2one(
        'account.account', string='Paid From Account',
        compute='_compute_disbursement_account', store=True, readonly=False,
        help="Credited when the loan is paid out. Defaults to the journal's "
             "default account.")
    move_id = fields.Many2one(
        'account.move', string='Disbursement Entry', readonly=True, copy=False)

    # Schedule & balances ---------------------------------------------
    line_ids = fields.One2many('hr.loan.line', 'loan_id', string='Repayment Schedule', copy=False)
    amount_paid = fields.Monetary(
        compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_remaining = fields.Monetary(
        compute='_compute_amounts', store=True, currency_field='currency_id')
    paid_percent = fields.Float(compute='_compute_amounts', store=True)
    paid_installments = fields.Integer(compute='_compute_amounts', store=True)
    pending_installments = fields.Integer(compute='_compute_amounts', store=True)
    next_deduction_date = fields.Date(compute='_compute_next_installment', store=True)
    next_installment_amount = fields.Monetary(
        compute='_compute_next_installment', store=True, currency_field='currency_id')

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('loan_amount', 'installment_amount')
    def _compute_installment_count(self):
        for loan in self:
            if loan.installment_amount > 0 and loan.loan_amount > 0:
                ratio = float_round(loan.loan_amount / loan.installment_amount, precision_digits=4)
                loan.installment_count = math.ceil(ratio)
            else:
                loan.installment_count = 0

    @api.depends('journal_id')
    def _compute_disbursement_account(self):
        for loan in self:
            loan.disbursement_account_id = loan.journal_id.default_account_id

    @api.depends('line_ids.state', 'line_ids.amount', 'loan_amount', 'state')
    def _compute_amounts(self):
        for loan in self:
            paid_lines = loan.line_ids.filtered(lambda l: l.state == 'paid')
            paid = sum(paid_lines.mapped('amount'))
            loan.amount_paid = paid
            loan.paid_installments = len(paid_lines)
            loan.pending_installments = len(loan.line_ids.filtered(lambda l: l.state == 'pending'))
            if loan.state == 'cancel':
                loan.amount_remaining = 0.0
            else:
                loan.amount_remaining = loan.loan_amount - paid
            loan.paid_percent = (paid / loan.loan_amount * 100.0) if loan.loan_amount else 0.0

    @api.depends('line_ids.state', 'line_ids.sequence', 'line_ids.due_date', 'line_ids.amount')
    def _compute_next_installment(self):
        for loan in self:
            pending = loan.line_ids.filtered(lambda l: l.state == 'pending').sorted('sequence')[:1]
            loan.next_deduction_date = pending.due_date if pending else False
            loan.next_installment_amount = pending.amount if pending else 0.0

    @api.depends('state', 'deduction_active', 'company_id.loan_deduction_paused')
    def _compute_deduction_status(self):
        for loan in self:
            if loan.state != 'running':
                loan.deduction_status = 'na'
            elif loan.company_id.loan_deduction_paused:
                loan.deduction_status = 'global_hold'
            elif not loan.deduction_active:
                loan.deduction_status = 'on_hold'
            else:
                loan.deduction_status = 'active'

    # ------------------------------------------------------------------
    # Constraints / ORM
    # ------------------------------------------------------------------
    @api.constrains('loan_amount', 'installment_amount')
    def _check_amounts(self):
        for loan in self:
            cur = loan.currency_id
            if cur.compare_amounts(loan.loan_amount, 0) <= 0:
                raise ValidationError(_("The loan amount must be greater than zero."))
            if cur.compare_amounts(loan.installment_amount, 0) <= 0:
                raise ValidationError(_("The monthly installment must be greater than zero."))
            if cur.compare_amounts(loan.installment_amount, loan.loan_amount) > 0:
                raise ValidationError(_("The monthly installment cannot be bigger than the loan amount."))

    _LOCKED_AFTER_DRAFT = {
        'employee_id', 'company_id', 'date', 'loan_amount', 'installment_amount',
        'first_deduction_date', 'journal_id', 'loan_account_id',
        'disbursement_account_id', 'create_disbursement_entry',
    }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.loan') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if self._LOCKED_AFTER_DRAFT & set(vals) and any(l.state != 'draft' for l in self):
            raise UserError(_("Loan terms can only be changed while the loan is in Draft."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_started(self):
        if any(l.state not in ('draft', 'cancel') for l in self):
            raise UserError(_("You can only delete draft or cancelled loans."))

    # ------------------------------------------------------------------
    # Security helper
    # ------------------------------------------------------------------
    @api.model
    def _check_manager(self):
        if not self.env.user.has_group('hr_employee_loan.group_loan_manager'):
            raise UserError(_("Only Loan Managers can do this."))

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _check_employee_contract(self):
        for loan in self:
            running = loan.employee_id.sudo().contract_ids.filtered(lambda c: c.state == 'open')
            if not running:
                raise UserError(_(
                    "%s has no running contract. Only employees with an active "
                    "contract can take a loan.") % loan.employee_id.name)

    def _check_accounting_setup(self):
        for loan in self:
            if not loan.loan_account_id:
                raise UserError(_("Please set the Loan Receivable Account on %s.") % loan.name)
            if loan.create_disbursement_entry:
                if not loan.journal_id:
                    raise UserError(_("Please set the Disbursement Journal on %s.") % loan.name)
                if not loan.disbursement_account_id:
                    raise UserError(_(
                        "Journal %s has no default account. Set 'Paid From Account' "
                        "on the loan.") % loan.journal_id.display_name)

    def _generate_lines(self):
        """One line per month; the last one carries the remainder."""
        self.ensure_one()
        cur = self.currency_id
        remaining = self.loan_amount
        vals = []
        for i in range(self.installment_count):
            amount = cur.round(min(self.installment_amount, remaining))
            remaining = cur.round(remaining - amount)
            vals.append({
                'loan_id': self.id,
                'sequence': i + 1,
                'due_date': self.first_deduction_date + relativedelta(months=i),
                'amount': amount,
            })
        self.env['hr.loan.line'].create(vals)

    def _create_disbursement_move(self):
        self.ensure_one()
        partner = self.employee_id.sudo().work_contact_id
        ref = _("Loan %(loan)s - %(emp)s", loan=self.name, emp=self.employee_id.name)
        move = self.env['account.move'].sudo().with_company(self.company_id).create({
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': ref,
            'line_ids': [
                (0, 0, {
                    'name': ref, 'account_id': self.loan_account_id.id,
                    'partner_id': partner.id or False,
                    'debit': self.loan_amount, 'credit': 0.0,
                }),
                (0, 0, {
                    'name': ref, 'account_id': self.disbursement_account_id.id,
                    'partner_id': partner.id or False,
                    'debit': 0.0, 'credit': self.loan_amount,
                }),
            ],
        })
        move.action_post()
        self.move_id = move

    def _preview_move_lines_vals(self):
        """Journal items shown in the confirmation preview (same as posted)."""
        self.ensure_one()
        partner = self.employee_id.sudo().work_contact_id
        ref = _("Loan %(loan)s - %(emp)s", loan=self.name, emp=self.employee_id.name)
        return [
            (0, 0, {'account_id': self.loan_account_id.id, 'partner_id': partner.id or False,
                    'name': ref, 'debit': self.loan_amount, 'credit': 0.0}),
            (0, 0, {'account_id': self.disbursement_account_id.id, 'partner_id': partner.id or False,
                    'name': ref, 'debit': 0.0, 'credit': self.loan_amount}),
        ]

    def action_open_confirm_wizard(self):
        """Confirm button: validate, then show the journal entry preview."""
        self._check_manager()
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Only draft loans can be confirmed."))
        self._check_employee_contract()
        self._check_accounting_setup()
        wizard = self.env['hr.loan.confirm.wizard'].create({
            'loan_id': self.id,
            'line_ids': self._preview_move_lines_vals() if self.create_disbursement_entry else [],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _("Confirm Loan"),
            'res_model': 'hr.loan.confirm.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        self._check_manager()
        for loan in self:
            if loan.state != 'draft':
                continue
            loan._check_employee_contract()
            loan._check_accounting_setup()
            loan._generate_lines()
            if loan.create_disbursement_entry:
                loan._create_disbursement_move()
            loan.state = 'running'
            loan.message_post(body=_("Loan confirmed: %(n)s installments of %(amt)s.",
                                     n=loan.installment_count, amt=loan.installment_amount))
        return True

    def action_cancel(self):
        self._check_manager()
        for loan in self:
            if loan.state not in ('draft', 'running'):
                raise UserError(_("Only draft or running loans can be cancelled."))
            if loan.line_ids.filtered(lambda l: l.state == 'paid'):
                raise UserError(_("%s already has paid installments and cannot be cancelled.") % loan.name)
            move = loan.move_id.sudo()
            if move and move.state == 'posted':
                move._reverse_moves(default_values_list=[{
                    'ref': _("Reversal of: %s", move.ref or move.name),
                    'date': fields.Date.context_today(loan),
                }], cancel=True)
            loan.line_ids.filtered(lambda l: l.state in ('pending', 'skipped')).write({'state': 'cancel'})
            loan.state = 'cancel'
        return True

    def _pause_deduction(self, reason):
        loans = self.filtered(lambda l: l.state == 'running' and l.deduction_active)
        loans.write({'deduction_active': False, 'pause_reason': reason})
        for loan in loans:
            self.env['hr.loan.pause.log'].sudo().create({
                'loan_id': loan.id, 'scope': 'loan', 'reason': reason})
            loan.message_post(body=_("Deduction paused: %s", reason))
        return True

    def action_resume_deduction(self):
        self._check_manager()
        loans = self.filtered(lambda l: l.state == 'running' and not l.deduction_active)
        loans.write({'deduction_active': True, 'pause_reason': False})
        loans.sudo().pause_log_ids.filtered(
            lambda r: r.scope == 'loan' and not r.date_end)._close()
        for loan in loans:
            loan.message_post(body=_("Deduction resumed."))
        return True

    # ------------------------------------------------------------------
    # Hold bookkeeping used by payroll
    # ------------------------------------------------------------------
    def _get_hold_reason(self):
        """Why this loan is NOT deducted right now (False when it is deducted)."""
        self.ensure_one()
        if self.state != 'running':
            return False
        if self.company_id.loan_deduction_paused:
            return _("All loans on hold: %s") % (
                self.company_id.loan_deduction_pause_reason or _("no reason given"))
        if not self.deduction_active:
            return _("Loan on hold: %s") % (self.pause_reason or _("no reason given"))
        return False

    def _get_open_pause_log(self):
        """The hold period that explains a skipped installment right now."""
        self.ensure_one()
        Log = self.env['hr.loan.pause.log'].sudo()
        scope = 'all' if self.company_id.loan_deduction_paused else 'loan'
        log = self.pause_log_ids.sudo().filtered(
            lambda r: r.scope == scope and not r.date_end)[:1]
        if not log and (scope == 'all' or not self.deduction_active):
            log = Log.create({
                'loan_id': self.id, 'scope': scope,
                'reason': (self.company_id.loan_deduction_pause_reason if scope == 'all'
                           else self.pause_reason)})
        return log

    def action_view_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
