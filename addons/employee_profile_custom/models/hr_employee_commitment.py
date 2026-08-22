# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployeeCommitment(models.Model):
    _name = 'hr.employee.commitment'
    _description = 'Employee Commitment / Agreement'
    _order = 'date_start desc, id desc'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, ondelete='cascade')
    name = fields.Char(string='Commitment Title', required=True)
    commitment_type = fields.Selection([
        ('bond', 'Service Bond'),
        ('nda', 'NDA'),
        ('training', 'Training Bond'),
        ('loan', 'Loan Agreement'),
        ('other', 'Other'),
    ], string='Type', default='other', required=True)
    description = fields.Text(string='Description')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('fulfilled', 'Fulfilled'),
        ('breached', 'Breached'),
    ], string='Status', default='draft', required=True)
    active = fields.Boolean(default=True)
