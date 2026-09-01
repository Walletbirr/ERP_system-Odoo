# -*- coding: utf-8 -*-
import calendar

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


MONTH_SELECTION = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
    ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
    ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December'),
]


class HrEmployeeAttendanceDays(models.Model):
    _name = 'hr.employee.attendance.days'
    _description = 'Employee Monthly Days Absent'
    _order = 'year desc, month desc, employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade')
    month = fields.Selection(
        MONTH_SELECTION, string='Month', required=True,
        default=lambda self: str(fields.Date.context_today(self).month))
    # Stored automatically, intentionally not shown on the views - HR only
    # ever deals with the current year in normal use.
    year = fields.Integer(
        string='Year', required=True,
        default=lambda self: fields.Date.context_today(self).year)
    days_absent = fields.Float(
        string='Days Absent', required=True, default=0.0,
        digits=(16, 1),
        help="Number of days this employee was absent during the selected month. "
             "Half days (e.g. 2.5) are allowed.")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)

    _sql_constraints = [
        ('uniq_employee_month_year',
         'unique(employee_id, month, year, company_id)',
         'An attendance record already exists for this employee for the selected month. '
         'Edit the existing record instead of creating a new one.'),
    ]

    @api.constrains('days_absent')
    def _check_days_absent_not_negative(self):
        for rec in self:
            if rec.days_absent < 0:
                raise ValidationError(_('Days absent cannot be negative.'))

    @api.constrains('days_absent', 'month', 'year')
    def _check_days_absent_within_month(self):
        month_label = dict(MONTH_SELECTION)
        for rec in self:
            days_in_month = calendar.monthrange(rec.year, int(rec.month))[1]
            if rec.days_absent > days_in_month:
                raise ValidationError(_(
                    'Days absent (%(days)s) cannot exceed the number of days in '
                    '%(month)s %(year)s (%(max)s days).'
                ) % {
                    'days': rec.days_absent,
                    'month': month_label.get(rec.month),
                    'year': rec.year,
                    'max': days_in_month,
                })

    def name_get(self):
        month_label = dict(MONTH_SELECTION)
        result = []
        for rec in self:
            name = "%s - %s %s" % (
                rec.employee_id.name or '', month_label.get(rec.month, ''), rec.year)
            result.append((rec.id, name))
        return result
