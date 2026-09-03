# -*- coding: utf-8 -*-
from odoo import fields, models


class LeaveLedgerLine(models.Model):
    _name = 'leave.ledger.line'
    _description = 'Leave Ledger Line (audit trail of every balance movement)'
    _order = 'date desc, id desc'

    allocation_id = fields.Many2one('leave.allocation', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(related='allocation_id.employee_id', store=True)
    leave_type_id = fields.Many2one(related='allocation_id.leave_type_id', store=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    move_type = fields.Selection([
        ('accrual', 'Accrual'),
        ('opening_balance', 'Opening Balance / Override'),
        ('quota_reset', 'Quota Reset'),
        ('carry_over', 'Carry-Over'),
        ('expiry', 'Expiry'),
        ('deduction', 'Deduction (Leave Taken)'),
        ('reversal', 'Reversal (Cancelled Leave)'),
        ('encashment', 'Encashment (Paid Out)'),
        ('manual_adjustment', 'Manual Adjustment'),
    ], required=True)
    amount = fields.Float(required=True, help="Positive = credit to balance, negative = debit.")
    reason = fields.Char()
    request_id = fields.Many2one('leave.request', string="Related Request", ondelete='set null')
    encashment_id = fields.Many2one('leave.encashment', string="Related Encashment", ondelete='set null')
    create_uid_display = fields.Char(compute='_compute_create_uid_display', string="Recorded By")

    def _compute_create_uid_display(self):
        for rec in self:
            rec.create_uid_display = rec.create_uid.name
