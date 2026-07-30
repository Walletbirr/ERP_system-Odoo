# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartnerClassification(models.Model):
    _name = 'res.partner.classification'
    _description = 'Contact Category'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help="Technical code used in domains/menus. "
             "Must be unique, e.g. 'internal', 'client', 'customer', 'company', 'vendor'."
    )
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color Index', default=0,
                            help="Used for kanban card color-coding.")
    icon = fields.Char(string='Icon', help="Font Awesome icon class, e.g. 'fa-briefcase'.")
    active = fields.Boolean(default=True)
    is_internal = fields.Boolean(
        string='Reserved for Internal Users',
        help="If checked, this category is auto-assigned to partners linked to a system "
             "user, and cannot be manually assigned to others."
    )
    partner_count = fields.Integer(compute='_compute_partner_count')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The category code must be unique.'),
    ]

    def _compute_partner_count(self):
        for rec in self:
            rec.partner_count = self.env['res.partner'].search_count(
                [('contact_type_id', '=', rec.id)]
            )

    def action_view_partners(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'res.partner',
            'view_mode': 'kanban,list,form',
            'domain': [('contact_type_id', '=', self.id)],
            'context': {'default_contact_type_id': self.id},
        }
