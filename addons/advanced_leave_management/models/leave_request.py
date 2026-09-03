# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class LeaveRequest(models.Model):
    _name = 'leave.request'
    _description = 'Leave Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc'

    name = fields.Char(default='New', copy=False, readonly=True)
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True, index=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True)
    leave_type_id = fields.Many2one('leave.type', required=True, tracking=True)
    request_unit = fields.Selection(related='leave_type_id.request_unit')

    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    duration_days = fields.Float(compute='_compute_duration_days', store=True, string="Duration (Days)")

    reason = fields.Text()
    attachment_ids = fields.Many2many('ir.attachment', string="Supporting Documents")

    # ---- Origin / approval routing -----------------------------------------
    origin = fields.Selection([
        ('hr_entry', 'Entered by HR'),
        ('self_service', 'Employee Self-Service'),
    ], default='hr_entry', required=True, readonly=True, copy=False,
        help="Determines whether this request requires approval. HR-entered leave is "
             "auto-confirmed; self-service requests always require Leave Officer approval.")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted - Pending Approval'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, copy=False)

    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)
    refusal_reason = fields.Text(copy=False)

    allocation_id = fields.Many2one('leave.allocation', compute='_compute_allocation_id', store=True)
    current_balance_display = fields.Float(related='allocation_id.current_balance', string="Available Balance")

    # -------------------------------------------------------------------
    # Sequence
    # -------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('leave.request') or 'New'
        return super().create(vals_list)

    # -------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------
    @api.depends('employee_id', 'leave_type_id')
    def _compute_allocation_id(self):
        Allocation = self.env['leave.allocation']
        for rec in self:
            rec.allocation_id = False
            if rec.employee_id and rec.leave_type_id:
                alloc = Allocation.search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('leave_type_id', '=', rec.leave_type_id.id),
                ], limit=1)
                if not alloc and rec.leave_type_id.allocation_type != 'no_allocation':
                    alloc = Allocation.create({
                        'employee_id': rec.employee_id.id,
                        'leave_type_id': rec.leave_type_id.id,
                    })
                rec.allocation_id = alloc

    @api.depends('date_from', 'date_to', 'employee_id')
    def _compute_duration_days(self):
        for rec in self:
            if not (rec.date_from and rec.date_to):
                rec.duration_days = 0.0
                continue
            calendar = rec.employee_id.resource_calendar_id
            if calendar:
                # Calendar-aware: excludes weekends/public holidays per the employee's
                # own working schedule, instead of counting raw calendar days.
                start_dt = fields.Datetime.to_datetime(rec.date_from).replace(hour=0, minute=0)
                end_dt = fields.Datetime.to_datetime(rec.date_to).replace(hour=23, minute=59)
                data = calendar.get_work_duration_data(
                    start_dt, end_dt, compute_leaves=True,
                    domain=[('company_id', 'in', [rec.company_id.id, False])],
                )
                rec.duration_days = data.get('days') or 0.0
            else:
                # No calendar configured on the employee: fall back to raw calendar days.
                rec.duration_days = (rec.date_to - rec.date_from).days + 1

    # -------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_("The start date must be before the end date."))

    @api.constrains('employee_id', 'date_from', 'date_to', 'state')
    def _check_overlap(self):
        for rec in self:
            if rec.state in ('refused', 'cancelled') or not (rec.date_from and rec.date_to):
                continue
            domain = [
                ('id', '!=', rec.id),
                ('employee_id', '=', rec.employee_id.id),
                ('state', 'not in', ('refused', 'cancelled')),
                ('date_from', '<=', rec.date_to),
                ('date_to', '>=', rec.date_from),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    "%(employee)s already has a leave request overlapping these dates.",
                    employee=rec.employee_id.name))

    # -------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------
    def _check_balance_guard(self):
        for rec in self:
            lt = rec.leave_type_id
            if lt.allocation_type == 'no_allocation':
                continue
            alloc = rec.allocation_id
            if not alloc:
                continue
            projected = alloc.current_balance - rec.duration_days
            if lt.allocation_type == 'accrual_bank' and not lt.allow_negative_balance and projected < 0:
                raise UserError(_(
                    "%(employee)s does not have enough balance for %(type)s "
                    "(available: %(bal).1f, requested: %(dur).1f).",
                    employee=rec.employee_id.name, type=lt.name,
                    bal=alloc.current_balance, dur=rec.duration_days))
            if lt.allocation_type == 'fixed_quota' and projected < 0:
                raise UserError(_(
                    "%(employee)s has exceeded the fixed quota for %(type)s "
                    "(available: %(bal).1f, requested: %(dur).1f).",
                    employee=rec.employee_id.name, type=lt.name,
                    bal=alloc.current_balance, dur=rec.duration_days))

    def _check_justification(self):
        for rec in self:
            if rec.leave_type_id.requires_justification and not rec.attachment_ids:
                raise UserError(_(
                    "%(type)s requires a supporting document before it can be submitted.",
                    type=rec.leave_type_id.name))

    def action_hr_confirm(self):
        """HR enters/confirms leave directly - no approval step. HR's action is final."""
        for rec in self:
            rec._check_justification()
            rec._check_balance_guard()
            rec.write({
                'state': 'approved',
                'origin': 'hr_entry',
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
            rec._post_deduction()

    def action_submit(self):
        """Employee self-service submission - always requires Leave Officer approval."""
        for rec in self:
            rec._check_justification()
            if rec.leave_type_id.min_notice_days and rec.date_from:
                delta = (rec.date_from - fields.Date.context_today(rec)).days
                if delta < rec.leave_type_id.min_notice_days:
                    raise UserError(_(
                        "%(type)s requires at least %(days)s days notice.",
                        type=rec.leave_type_id.name, days=rec.leave_type_id.min_notice_days))
            rec.write({'state': 'submitted', 'origin': 'self_service'})
            rec.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Leave request pending approval'),
                note=_('%(emp)s requested %(type)s from %(df)s to %(dt)s.',
                       emp=rec.employee_id.name, type=rec.leave_type_id.name,
                       df=rec.date_from, dt=rec.date_to),
                user_id=self.env.ref('advanced_leave_management.group_leave_officer').users[:1].id
                if self.env.ref('advanced_leave_management.group_leave_officer').users else self.env.user.id,
            )

    def action_approve(self):
        """Leave Officer approval - only path this button matters for is self_service."""
        officer_group = self.env.ref('advanced_leave_management.group_leave_officer')
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Only submitted requests can be approved."))
            if self.env.user not in officer_group.users:
                raise UserError(_("Only a Leave Officer can approve requests."))
            allowed = rec.leave_type_id.responsible_officer_ids
            if allowed and self.env.user not in allowed:
                raise UserError(_("You are not a designated Leave Officer for this leave type."))
            rec._check_balance_guard()
            rec.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
            rec._post_deduction()
            rec.activity_ids.filtered(lambda a: a.summary == _('Leave request pending approval')).unlink()

    def action_refuse(self):
        officer_group = self.env.ref('advanced_leave_management.group_leave_officer')
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Only submitted requests can be refused."))
            if self.env.user not in officer_group.users:
                raise UserError(_("Only a Leave Officer can refuse requests."))
            rec.write({'state': 'refused'})
            rec.activity_ids.unlink()

    def action_cancel(self):
        """Cancels an approved leave and reverses the ledger deduction."""
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_("Only approved requests can be cancelled."))
            if rec.allocation_id and rec.leave_type_id.allocation_type != 'no_allocation':
                rec.allocation_id._add_ledger_line(
                    move_type='reversal',
                    amount=rec.duration_days,
                    reason=_('Cancellation of %(name)s', name=rec.name),
                    request_id=rec.id,
                )
            rec.state = 'cancelled'

    def _post_deduction(self):
        for rec in self:
            if rec.allocation_id and rec.leave_type_id.allocation_type != 'no_allocation':
                rec.allocation_id._add_ledger_line(
                    move_type='deduction',
                    amount=-rec.duration_days,
                    reason=_('Leave taken: %(name)s', name=rec.name),
                    request_id=rec.id,
                )
