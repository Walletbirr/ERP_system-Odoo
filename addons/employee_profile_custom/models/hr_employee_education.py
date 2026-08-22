# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployeeEducation(models.Model):
    _name = 'hr.employee.education'
    _description = 'Employee Education'
    _order = 'date_end desc, date_start desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade')

    name = fields.Char(
        string='Summary', compute='_compute_name', store=True)

    education_level = fields.Selection([
        ('high_school', 'High School'),
        ('diploma', 'Diploma'),
        ('bachelor', 'Bachelor'),
        ('master', 'Master'),
        ('phd', 'PhD'),
        ('other', 'Other'),
    ], string='Education Level', required=True, default='bachelor')

    institution_name = fields.Char(string='Institution Name', required=True)
    field_of_study = fields.Char(string='Field of Study / Major')
    degree = fields.Char(
        string='Degree / Qualification',
        help="e.g. B.Sc., B.A., Diploma, Certificate")

    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date / Graduation Date')

    status = fields.Selection([
        ('completed', 'Completed'),
        ('ongoing', 'Ongoing'),
        ('dropped', 'Dropped'),
    ], string='Status', default='completed', required=True)

    grade = fields.Char(string='Grade / GPA')

    country_id = fields.Many2one('res.country', string='Country')
    city = fields.Char(string='City')

    certificate_document = fields.Binary(string='Certificate / Document')
    certificate_document_filename = fields.Char(string='Document Filename')

    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    @api.depends('education_level', 'degree', 'field_of_study', 'institution_name')
    def _compute_name(self):
        level_labels = dict(self._fields['education_level'].selection)
        for rec in self:
            label = rec.degree or level_labels.get(rec.education_level, '')
            parts = [p for p in (label, rec.field_of_study, rec.institution_name) if p]
            rec.name = ' - '.join(parts) or 'New Education Entry'
