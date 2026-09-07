# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class LeaveEncashment(models.Model):
    _name = 'leave.encashment'
    _description = 'Leave Encashment (Pay Out Unused Leave)'
    _inherit = ['mail.thread']
    _order = 'date desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    leave_type_id = fields.Many2one(
        'leave.type', required=True, tracking=True,
        domain=[('allocation_type', 'in', ('accrual_bank', 'fixed_quota'))],
        default=lambda self: self.env.ref(
            'advanced_leave_management.leave_type_annual', raise_if_not_found=False),
        help="Only leave types that track a balance can be encashed. Defaults to Annual "
             "Leave since that's the only type Binget encashes; still changeable if needed.")
    allocation_id = fields.Many2one('leave.allocation', compute='_compute_allocation_id', store=True)
    available_balance = fields.Float(related='allocation_id.current_balance', string="Available Balance")

    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    days = fields.Float(string="Days to Encash", required=True, tracking=True)

    basic_salary = fields.Monetary(string="Monthly Basic Salary", tracking=True)
    days_in_month = fields.Integer(
        string="Days per Month", default=lambda self: self.env.company.leave_encashment_days_in_month or 30)
    daily_rate = fields.Monetary(string="Daily Rate", tracking=True)
    amount = fields.Monetary(string="Gross Encashment Amount", required=True, tracking=True)

    tax_rate = fields.Float(
        string="Tax Rate (%)", tracking=True,
        help="Auto-selected from the Tax Bracket table based on the employee's monthly "
             "salary (Leave Management > Configuration > Tax Brackets). Editable if you "
             "need to override for a specific case.")
    tax_amount = fields.Monetary(string="Tax Withheld", tracking=True)
    net_amount = fields.Monetary(string="Net Payable to Employee", tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, copy=False)
    move_id = fields.Many2one('account.move', string="Journal Entry", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('leave.encashment') or 'New'
        return super().create(vals_list)

    @api.depends('employee_id', 'leave_type_id')
    def _compute_allocation_id(self):
        Allocation = self.env['leave.allocation']
        for rec in self:
            rec.allocation_id = False
            if rec.employee_id and rec.leave_type_id:
                rec.allocation_id = Allocation.search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('leave_type_id', '=', rec.leave_type_id.id),
                ], limit=1)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Best-effort pull of the current wage if the Contracts module is installed
        and the employee has one. Always editable afterward - this is a starting
        point, not an authoritative payroll figure."""
        for rec in self:
            if not rec.employee_id:
                continue
            contract = getattr(rec.employee_id, 'contract_id', False)
            if contract and 'wage' in contract._fields:
                rec.basic_salary = contract.wage

    @api.onchange('basic_salary', 'days_in_month')
    def _onchange_rate_inputs(self):
        for rec in self:
            rec.daily_rate = (rec.basic_salary / rec.days_in_month) if rec.days_in_month else 0.0
            # Bracket lookup uses the employee's gross monthly salary - the same logic a
            # human payroll clerk uses: "what bracket does this person's income sit in".
            # This picks ONE bracket's rate for the whole leave amount; it is not a full
            # marginal calculation split across brackets, but it is correct whenever the
            # salary already sits inside a single bracket range, and always correct for
            # the top bracket (which is the common case for higher earners).
            if rec.basic_salary:
                rec.tax_rate = self.env['leave.tax.bracket']._get_rate_for_amount(
                    rec.basic_salary, rec.company_id)

    @api.onchange('basic_salary', 'days_in_month', 'days')
    def _onchange_amount_inputs(self):
        # amount is computed straight from basic_salary/days_in_month rather than from
        # daily_rate, because daily_rate is a Monetary field and Odoo rounds Monetary
        # values to currency precision the instant they're assigned - so daily_rate is
        # already rounded to 2718.39 before this ever runs. Multiplying that rounded
        # value by 18 days silently amplified a sub-cent rounding residual into a full
        # cent (2718.39 x 18 = 48,931.02 vs the true 81,551.72/30 x 18 = 48,931.032,
        # i.e. 48,931.03). daily_rate stays as a rounded figure for display only.
        for rec in self:
            rec.amount = round(
                (rec.basic_salary / rec.days_in_month * rec.days) if rec.days_in_month else 0.0, 2)

    @api.onchange('amount', 'tax_rate')
    def _onchange_tax(self):
        for rec in self:
            rec.tax_amount = round(rec.amount * (rec.tax_rate / 100.0), 2)
            rec.net_amount = round(rec.amount - rec.tax_amount, 2)

    def action_post(self):
        Company = self.env.company
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only draft encashments can be posted."))
            if not rec.allocation_id:
                raise UserError(_("This employee has no balance for %s.", rec.leave_type_id.name))
            if rec.days <= 0:
                raise UserError(_("Days to encash must be greater than zero."))
            if rec.days > rec.allocation_id.current_balance:
                raise UserError(_(
                    "Cannot encash %(days).1f days - %(emp)s only has %(bal).1f available.",
                    days=rec.days, emp=rec.employee_id.name, bal=rec.allocation_id.current_balance))
            if rec.amount <= 0:
                raise UserError(_("Encashment amount must be greater than zero."))
            if rec.net_amount < 0:
                raise UserError(_("Tax withheld cannot exceed the gross amount."))

            expense_acc = Company.leave_encashment_expense_account_id
            payable_acc = Company.leave_encashment_payable_account_id
            tax_payable_acc = Company.leave_encashment_tax_payable_account_id
            journal = Company.leave_encashment_journal_id
            if not (expense_acc and payable_acc and journal) or (
                    rec.tax_amount and not tax_payable_acc):
                raise UserError(_(
                    "Leave Encashment accounts/journal are not configured. Go to Leave "
                    "Management > Configuration > Encashment Settings and set the Expense "
                    "Account, Net Payable Account, Tax Payable Account, and Journal first."))

            description = _("Leave encashment - %(emp)s - %(type)s",
                             emp=rec.employee_id.name, type=rec.leave_type_id.name)
            narration = _(
                "%(desc)s - %(days).1f day(s): gross %(gross).2f, tax withheld %(tax).2f "
                "at %(rate).1f%%, net %(net).2f", desc=description, days=rec.days,
                gross=rec.amount, tax=rec.tax_amount, rate=rec.tax_rate, net=rec.net_amount)

            partner = (rec.employee_id.work_contact_id.id
                       if rec.employee_id.work_contact_id else False)

            line_vals = [
                (0, 0, {
                    'account_id': expense_acc.id,
                    'name': description,
                    'debit': rec.amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'account_id': payable_acc.id,
                    'name': description,
                    'debit': 0.0,
                    'credit': rec.net_amount,
                    'partner_id': partner,
                }),
            ]
            if rec.tax_amount:
                line_vals.append((0, 0, {
                    'account_id': tax_payable_acc.id,
                    'name': description,
                    'debit': 0.0,
                    'credit': rec.tax_amount,
                }))

            move = self.env['account.move'].sudo().create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': rec.date,
                'ref': rec.name,
                'narration': narration,
                'line_ids': line_vals,
            })
            move.sudo().action_post()

            rec.allocation_id._add_ledger_line(
                move_type='encashment',
                amount=-rec.days,
                date=rec.date,
                reason=_("Encashment %s", rec.name),
                request_id=False,
            )
            self.env['leave.ledger.line'].search([
                ('reason', '=', _("Encashment %s", rec.name)),
                ('allocation_id', '=', rec.allocation_id.id),
            ], limit=1, order='id desc').write({'encashment_id': rec.id})

            rec.write({'state': 'posted', 'move_id': move.id})

    def action_cancel(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_(
                    "Only draft encashments can be cancelled directly. A posted encashment "
                    "has a real journal entry - reverse it from the Accounting app first, "
                    "then contact an administrator to correct the leave ledger."))
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_("Only posted encashments can be reset to draft."))
            if rec.move_id:
                move = rec.move_id.sudo()
                # This button is admin-only (base.group_system), so it's trusted to
                # handle the journal entry itself rather than requiring a manual trip
                # to Accounting first. Odoo's own accounting-integrity checks (locked
                # period, hashed/secured entries, etc.) still apply and will raise
                # their own clear error here if this move genuinely can't be touched -
                # that block is intentional and is not caught/bypassed.
                if move.state == 'posted':
                    move.button_draft()
                move.unlink()
            rec.write({'state': 'draft', 'move_id': False})

    def unlink(self):
        for rec in self:
            if rec.state == 'posted':
                raise UserError(_("Posted encashments cannot be deleted. Reverse the journal "
                                   "entry from Accounting instead."))
        return super().unlink()
