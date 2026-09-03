# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LeaveAllocation(models.Model):
    _name = 'leave.allocation'
    _description = 'Employee Leave Allocation (current bank per leave type)'
    _rec_name = 'display_name'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    leave_type_id = fields.Many2one('leave.type', required=True, ondelete='restrict')
    company_id = fields.Many2one(related='employee_id.company_id', store=True)

    ledger_line_ids = fields.One2many('leave.ledger.line', 'allocation_id', string="Ledger")
    current_balance = fields.Float(compute='_compute_current_balance', store=True,
                                    help="Sum of all ledger movements. This is the live balance.")
    last_accrual_date = fields.Date(
        help="Last date the accrual engine granted days for this allocation. "
             "Used to compute the next accrual run; reset by an opening-balance override.")
    display_name = fields.Char(compute='_compute_display_name')

    _sql_constraints = [
        ('employee_leave_type_uniq', 'unique(employee_id, leave_type_id)',
         'An employee can only have one allocation record per leave type.'),
    ]

    @api.depends('employee_id', 'leave_type_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.employee_id.name} - {rec.leave_type_id.name}"

    @api.depends('ledger_line_ids.amount')
    def _compute_current_balance(self):
        for rec in self:
            rec.current_balance = sum(rec.ledger_line_ids.mapped('amount'))

    def _add_ledger_line(self, move_type, amount, date=None, reason='', request_id=False):
        self.ensure_one()
        return self.env['leave.ledger.line'].create({
            'allocation_id': self.id,
            'move_type': move_type,
            'amount': amount,
            'date': date or fields.Date.context_today(self),
            'reason': reason,
            'request_id': request_id,
        })

    def action_set_opening_balance(self, amount, effective_date, reason, set_by_uid=False):
        """Migration / correction entry point. Records an auditable opening-balance
        ledger line and moves last_accrual_date forward so the accrual cron computes
        future growth from this new baseline instead of the original contract date.
        """
        self.ensure_one()
        current = self.current_balance
        delta = amount - current
        self._add_ledger_line(
            move_type='opening_balance',
            amount=delta,
            date=effective_date,
            reason=reason or 'Opening balance override',
        )
        self.last_accrual_date = effective_date
