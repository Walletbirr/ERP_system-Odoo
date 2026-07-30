# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    contact_type_id = fields.Many2one(
        'res.partner.classification',
        string='Contact Category',
        index=True,
        tracking=True,
        help="Classifies this contact for display, security and reporting purposes."
    )
    contact_type_code = fields.Char(
        related='contact_type_id.code', store=True, index=True, readonly=True
    )
    category_color = fields.Integer(related='contact_type_id.color', readonly=True)

    @api.onchange('contact_type_id')
    def _onchange_contact_type_id(self):
        if self.contact_type_id.code == 'company':
            self.is_company = True

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners._auto_assign_internal_classification()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if 'user_ids' in vals:
            self._auto_assign_internal_classification()
        return res

    def _auto_assign_internal_classification(self):
        """Any partner linked to a res.users record is forced into the
        'internal' category, overriding whatever was manually set, so this
        classification can't be spoofed to dodge the security rules below."""
        internal_cat = self.env['res.partner.classification'].search(
            [('code', '=', 'internal')], limit=1
        )
        if not internal_cat:
            return
        for partner in self:
            if partner.user_ids and partner.contact_type_id != internal_cat:
                partner.contact_type_id = internal_cat.id
            elif not partner.user_ids and partner.contact_type_id == internal_cat:
                # Fell back to default category if the linked user was removed
                default_cat = self.env['res.partner.classification'].search(
                    [('code', '=', 'customer')], limit=1
                )
                if default_cat:
                    partner.contact_type_id = default_cat.id
