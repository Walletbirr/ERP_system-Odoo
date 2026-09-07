# -*- coding: utf-8 -*-
import json

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
    absence_dates = fields.Text(
        string='Absence Dates', default='[]',
        help="Technical field: JSON list of ISO dates (YYYY-MM-DD) the "
             "employee was marked absent, picked from the calendar widget. "
             "Not meant to be edited directly.")
    days_absent = fields.Float(
        string='Days Absent', compute='_compute_days_absent', store=True,
        digits=(16, 1),
        help="Number of days this employee was absent during the selected "
             "month. Derived automatically from the dates picked on the "
             "calendar - pick the specific absent dates rather than "
             "entering a number.")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)

    _sql_constraints = [
        ('uniq_employee_month_year',
         'unique(employee_id, month, year, company_id)',
         'An attendance record already exists for this employee for the selected month. '
         'Edit the existing record instead of creating a new one.'),
    ]

    def _get_absence_date_list(self):
        """Return the sorted, de-duplicated list of ISO date strings stored
        on this record. Defensive against malformed/empty JSON."""
        self.ensure_one()
        try:
            raw = json.loads(self.absence_dates or '[]')
        except ValueError:
            return []
        if not isinstance(raw, list):
            return []
        return sorted({d for d in raw if isinstance(d, str) and d})

    @api.depends('absence_dates')
    def _compute_days_absent(self):
        for rec in self:
            rec.days_absent = len(rec._get_absence_date_list())

    @api.constrains('absence_dates', 'month', 'year')
    def _check_absence_dates_within_month(self):
        month_label = dict(MONTH_SELECTION)
        for rec in self:
            expected_prefix = '%04d-%02d-' % (rec.year, int(rec.month))
            for date_str in rec._get_absence_date_list():
                if not date_str.startswith(expected_prefix):
                    raise ValidationError(_(
                        'Absence date %(date)s is outside %(month)s %(year)s. '
                        'Only dates within the selected month can be marked absent.'
                    ) % {
                        'date': date_str,
                        'month': month_label.get(rec.month),
                        'year': rec.year,
                    })

    @api.onchange('month', 'year')
    def _onchange_month_year_prune_dates(self):
        """If HR changes the month/year after already picking dates, drop
        any picked dates that no longer belong to the newly selected month
        instead of leaving stale/invalid dates behind."""
        for rec in self:
            if not rec.absence_dates or rec.absence_dates == '[]':
                continue
            expected_prefix = '%04d-%02d-' % (rec.year, int(rec.month))
            kept = [d for d in rec._get_absence_date_list() if d.startswith(expected_prefix)]
            rec.absence_dates = json.dumps(kept)

    def name_get(self):
        month_label = dict(MONTH_SELECTION)
        result = []
        for rec in self:
            name = "%s - %s %s" % (
                rec.employee_id.name or '', month_label.get(rec.month, ''), rec.year)
            result.append((rec.id, name))
        return result
