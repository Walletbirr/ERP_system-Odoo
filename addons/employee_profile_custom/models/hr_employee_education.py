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

    # ------------------------------------------------------------------
    # These four fields are configurable master data, managed under
    # Employees > Configuration > Educational Background (same pattern
    # as core Odoo's Employee Tags). HR can add/rename/archive options
    # there without touching code.
    # ------------------------------------------------------------------
    education_level = fields.Many2one(
        'hr.employee.education.level', string='Education Level', required=True)
    institution_name = fields.Many2one(
        'hr.employee.education.institution', string='Institution Name', required=True)
    field_of_study = fields.Many2one(
        'hr.employee.education.field', string='Field of Study / Major')
    degree = fields.Many2one(
        'hr.employee.education.degree', string='Degree / Qualification',
        help="e.g. B.Sc., B.A., Diploma, Certificate")

    date_start = fields.Date(string='Start Date', required=True)
    date_end = fields.Date(string='End Date / Graduation Date', required=True)

    status = fields.Selection([
        ('completed', 'Completed'),
        ('ongoing', 'Ongoing'),
        ('dropped', 'Dropped'),
    ], string='Status', default='completed', required=True)

    grade = fields.Char(string='Grade / GPA')

    country_id = fields.Many2one(
        'res.country', string='Country',
        default=lambda self: self.env['res.country'].search(
            [('code', '=', 'ET')], limit=1).id)
    city = fields.Char(string='City')

    certificate_document = fields.Binary(string='Certificate / Document')
    certificate_document_filename = fields.Char(string='Document Filename')

    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    @api.depends('education_level', 'degree', 'field_of_study', 'institution_name')
    def _compute_name(self):
        for rec in self:
            label = rec.degree.name if rec.degree else (rec.education_level.name or '')
            parts = [
                p for p in (label, rec.field_of_study.name, rec.institution_name.name)
                if p
            ]
            rec.name = ' - '.join(parts) or 'New Education Entry'
