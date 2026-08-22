# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployeeCertification(models.Model):
    _name = 'hr.employee.certification'
    _description = 'Employee Certification'
    _order = 'issue_date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade')

    name = fields.Char(string='Certification Title', required=True)
    issuing_organization = fields.Char(string='Issuing Organization')
    credential_id = fields.Char(string='Credential ID')

    issue_date = fields.Date(string='Issue Date')
    expiry_date = fields.Date(string='Expiry Date')

    status = fields.Selection([
        ('valid', 'Valid'),
        ('expiring_soon', 'Expiring Soon'),
        ('expired', 'Expired'),
        ('no_expiry', 'No Expiry'),
    ], string='Status', compute='_compute_status', store=True)

    certificate_document = fields.Binary(string='Certificate / Document')
    certificate_document_filename = fields.Char(string='Document Filename')

    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    @api.depends('expiry_date')
    def _compute_status(self):
        today = fields.Date.context_today(self)
        soon = fields.Date.add(today, days=30)
        for rec in self:
            if not rec.expiry_date:
                rec.status = 'no_expiry'
            elif rec.expiry_date < today:
                rec.status = 'expired'
            elif rec.expiry_date <= soon:
                rec.status = 'expiring_soon'
            else:
                rec.status = 'valid'
