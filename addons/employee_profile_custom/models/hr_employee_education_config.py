# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeeEducationLevel(models.Model):
    """Configurable list of education levels (Employees > Configuration).

    Replaces the old hard-coded Selection on hr.employee.education so HR
    can add/rename/archive levels without touching code, the same way
    Employee Tags (hr.employee.category) are managed.
    """
    _name = 'hr.employee.education.level'
    _description = 'Employee Education Level'
    _order = 'sequence, name'

    name = fields.Char(string='Education Level', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name, active)', 'This education level already exists.'),
    ]


class HrEmployeeEducationInstitution(models.Model):
    """Configurable list of institutions/universities (Employees > Configuration)."""
    _name = 'hr.employee.education.institution'
    _description = 'Employee Education Institution'
    _order = 'name'

    name = fields.Char(string='Institution Name', required=True, translate=True)
    country_id = fields.Many2one(
        'res.country', string='Country',
        default=lambda self: self.env['res.country'].search(
            [('code', '=', 'ET')], limit=1).id)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name, active)', 'This institution already exists.'),
    ]


class HrEmployeeEducationField(models.Model):
    """Configurable list of fields of study / majors (Employees > Configuration)."""
    _name = 'hr.employee.education.field'
    _description = 'Employee Field of Study'
    _order = 'name'

    name = fields.Char(string='Field of Study', required=True, translate=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name, active)', 'This field of study already exists.'),
    ]


class HrEmployeeEducationDegree(models.Model):
    """Configurable list of degrees / qualifications (Employees > Configuration)."""
    _name = 'hr.employee.education.degree'
    _description = 'Employee Degree / Qualification'
    _order = 'sequence, name'

    name = fields.Char(string='Degree / Qualification', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name, active)', 'This degree already exists.'),
    ]
