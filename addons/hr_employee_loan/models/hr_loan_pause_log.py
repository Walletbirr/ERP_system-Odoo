# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrLoanPauseLog(models.Model):
    """One row per hold period of a loan's deduction (own hold or company-wide)."""
    _name = 'hr.loan.pause.log'
    _description = 'Loan Deduction Pause History'
    _order = 'date_start desc, id desc'

    loan_id = fields.Many2one('hr.loan', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(related='loan_id.employee_id', store=True, index=True)
    company_id = fields.Many2one(related='loan_id.company_id', store=True)
    scope = fields.Selection([
        ('loan', 'This loan only'),
        ('all', 'All loans (company-wide)'),
    ], string='Scope', required=True, default='loan')
    reason = fields.Char(string='Reason')
    date_start = fields.Datetime(string='Paused On', required=True, default=fields.Datetime.now)
    date_end = fields.Datetime(string='Resumed On')
    user_id = fields.Many2one('res.users', string='Paused By', default=lambda self: self.env.user)
    resumed_by_id = fields.Many2one('res.users', string='Resumed By')
    is_open = fields.Boolean(compute='_compute_is_open', store=True, string='Still On Hold')
    skipped_line_ids = fields.One2many('hr.loan.line', 'pause_log_id', string='Skipped Installments')
    skipped_count = fields.Integer(string='Installments Skipped', compute='_compute_skipped_count')

    @api.depends('date_end')
    def _compute_is_open(self):
        for rec in self:
            rec.is_open = not rec.date_end

    @api.depends('skipped_line_ids')
    def _compute_skipped_count(self):
        for rec in self:
            rec.skipped_count = len(rec.skipped_line_ids)

    def _close(self):
        self.filtered(lambda r: not r.date_end).write({
            'date_end': fields.Datetime.now(),
            'resumed_by_id': self.env.user.id,
        })
