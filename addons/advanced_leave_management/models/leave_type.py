# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LeaveType(models.Model):
    _name = 'leave.type'
    _description = 'Leave Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(help="Short code, e.g. AL, SL, ML. Used in reports/payroll export.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string="Color", default=0)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    # ---- Balance behavior -------------------------------------------------
    allocation_type = fields.Selection([
        ('no_allocation', 'No Allocation (unlimited / unpaid)'),
        ('fixed_quota', 'Fixed Quota (non-accruing, resets on schedule)'),
        ('accrual_bank', 'Accrual Bank (formula-based, ledger tracked)'),
    ], string="Balance Type", required=True, default='accrual_bank',
        help="Determines how balances are tracked for this leave type:\n"
             "- No Allocation: no balance is tracked at all (e.g. Unpaid Leave).\n"
             "- Fixed Quota: a flat number of days per year/event, no accrual formula.\n"
             "- Accrual Bank: draws from the formula-based accrual ledger.")

    request_unit = fields.Selection([
        ('day', 'Full Day(s)'),
        ('half_day', 'Half Day'),
        ('hour', 'Hour(s)'),
    ], default='day', required=True)

    # ---- Accrual Bank config ------------------------------------------------
    base_days = fields.Float(string="Base Days (at contract start)", default=16.0)
    increment_per_year = fields.Float(string="Increment per Year of Service", default=1.0)
    increment_frequency_months = fields.Integer(
        string="Increment Frequency (months)", default=12,
        help="How often the entitlement grows, in months. 12 = once per work anniversary.")
    max_days = fields.Float(string="Maximum Cap (0 = no cap)", default=0.0)
    allow_negative_balance = fields.Boolean(
        string="Allow Taking in Advance",
        help="If enabled, employees may request more than their current accrued balance.")

    # ---- Fixed Quota config ---------------------------------------------
    quota_days = fields.Float(string="Quota Days")
    quota_reset = fields.Selection([
        ('yearly', 'Every Calendar Year'),
        ('per_event', 'Per Event (no automatic reset)'),
    ], string="Quota Reset", default='yearly')

    # ---- Carry-over (Accrual Bank & Fixed Quota) --------------------------
    carry_over_allowed = fields.Boolean(string="Allow Carry-Over")
    carry_over_max_days = fields.Float(string="Max Carry-Over Days")
    carry_over_expiry_months = fields.Integer(
        string="Carried-Over Days Expire After (months)",
        help="Carried-over days not used within this many months are forfeited. 0 = never expire.")

    # ---- Eligibility / requirements ---------------------------------------
    applicable_gender = fields.Selection([
        ('all', 'All'),
        ('male', 'Male Only'),
        ('female', 'Female Only'),
    ], default='all')
    applicable_contract_type_ids = fields.Many2many(
        'hr.contract.type', string="Applicable Contract Types",
        help="Leave empty to apply to all contract types.")
    requires_justification = fields.Boolean(
        string="Requires Supporting Document",
        help="If enabled, an attachment (e.g. medical certificate) is mandatory before this "
             "leave request can be submitted.")
    min_notice_days = fields.Integer(
        string="Minimum Notice (days)",
        help="Minimum number of days in advance a self-service request must be submitted. "
             "0 = no restriction. Does not apply to HR-entered leave.")

    responsible_officer_ids = fields.Many2many(
        'res.users', string="Leave Officers for this Type",
        domain=lambda self: [('groups_id', 'in', self.env.ref(
            'advanced_leave_management.group_leave_officer').id)],
        help="Optional. If left empty, ANY member of the Leave Officer group may approve "
             "requests of this type. If set, only these officers may approve.")

    @api.onchange('allocation_type')
    def _onchange_allocation_type(self):
        if self.allocation_type != 'accrual_bank':
            self.allow_negative_balance = False
        if self.allocation_type == 'no_allocation':
            self.carry_over_allowed = False
