# -*- coding: utf-8 -*-
from odoo import fields, models


class LeavePolicy(models.Model):
    _name = 'leave.policy'
    _description = 'Leave Policy (scopes a Leave Type to part of the organization)'

    name = fields.Char(required=True)
    leave_type_id = fields.Many2one('leave.type', required=True, string="Leave Type")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    department_ids = fields.Many2many(
        'hr.department', string="Departments",
        help="Leave empty to apply company-wide.")
    active = fields.Boolean(default=True)
