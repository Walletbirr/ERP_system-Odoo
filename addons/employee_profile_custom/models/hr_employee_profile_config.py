# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeeGender(models.Model):
    """Configurable list of genders (Employees > Configuration).

    Drives hr.employee.gender_id, the field actually shown on the
    Employee Profile UI. HR can add/rename/archive options (e.g. remove
    an unwanted "Other" entry) without touching code - the core
    hr.employee.gender Selection field is kept in sync automatically
    (see hr_employee.py) purely so any other installed app that still
    reads/writes it keeps working.
    """
    _name = 'hr.employee.gender'
    _description = 'Employee Gender'
    _order = 'sequence, name'

    name = fields.Char(string='Gender', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name, active)', 'This gender already exists.'),
    ]


class HrEmployeeMaritalStatus(models.Model):
    """Configurable list of marital statuses (Employees > Configuration)."""
    _name = 'hr.employee.marital.status'
    _description = 'Employee Marital Status'
    _order = 'sequence, name'

    name = fields.Char(string='Marital Status', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name, active)', 'This marital status already exists.'),
    ]


class HrEmployeeBloodType(models.Model):
    """Configurable list of blood types (Employees > Configuration)."""
    _name = 'hr.employee.blood.type'
    _description = 'Employee Blood Type'
    _order = 'sequence, name'

    name = fields.Char(string='Blood Type', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name, active)', 'This blood type already exists.'),
    ]
