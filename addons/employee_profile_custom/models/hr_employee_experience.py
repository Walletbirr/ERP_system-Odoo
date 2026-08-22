# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployeeExperience(models.Model):
    _name = 'hr.employee.experience'
    _description = 'Employee Work Experience'
    _order = 'date_start desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade')

    name = fields.Char(
        string='Summary', compute='_compute_name', store=True)

    company_name = fields.Char(
        string='Company / Organization', required=True,
        help='Previous employer name')

    job_title = fields.Char(
        string='Job Title / Position', required=True,
        help='Position held')

    employment_type = fields.Selection([
        ('full_time', 'Full-time'),
        ('part_time', 'Part-time'),
        ('contract', 'Contract'),
        ('internship', 'Internship'),
        ('freelance', 'Freelance'),
        ('temporary', 'Temporary'),
        ('other', 'Other'),
    ], string='Employment Type', default='full_time')

    department = fields.Char(string='Department')

    date_start = fields.Date(string='Start Date', required=True)
    date_end = fields.Date(string='End Date')
    currently_working = fields.Boolean(
        string='Currently Working', default=False)

    location = fields.Char(
        string='Location', help='City / Country')

    responsibilities = fields.Text(
        string='Responsibilities',
        help='Main duties and responsibilities')
    achievements = fields.Text(
        string='Achievements',
        help='Major accomplishments')
    reason_for_leaving = fields.Char(
        string='Reason for Leaving')

    reference_name = fields.Char(
        string='Reference Name',
        help='Previous employer / reference person')
    reference_contact = fields.Char(
        string='Reference Contact',
        help='Phone or email of the reference')

    certificate_document = fields.Binary(string='Experience Certificate')
    certificate_document_filename = fields.Char(string='Document Filename')

    description = fields.Text(string='Notes')
    active = fields.Boolean(default=True)

    @api.depends('company_name', 'job_title')
    def _compute_name(self):
        for rec in self:
            parts = [p for p in (rec.job_title, rec.company_name) if p]
            rec.name = ' @ '.join(parts) if parts else 'New Experience'

    @api.onchange('currently_working')
    def _onchange_currently_working(self):
        if self.currently_working:
            self.date_end = False
