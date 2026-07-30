# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartnerClassificationWizard(models.TransientModel):
    _name = 'res.partner.classification.wizard'
    _description = 'Bulk Categorize Contacts'

    contact_type_id = fields.Many2one(
        'res.partner.classification',
        string='Set Category To',
        required=True,
        options={'no_create': True},
    )

    def action_apply(self):
        self.ensure_one()
        partner_ids = self.env.context.get('active_ids', [])
        partners = self.env['res.partner'].browse(partner_ids).exists()

        # Never let a bulk action override the auto-managed Internal User
        # category - those stay tied to whether a system user is linked.
        internal_locked = partners.filtered(lambda p: p.user_ids)
        target = partners - internal_locked

        target.write({'contact_type_id': self.contact_type_id.id})

        message = f"{len(target)} contact(s) set to '{self.contact_type_id.name}'."
        if internal_locked:
            message += (
                f" {len(internal_locked)} contact(s) skipped because they are "
                "linked to a system user (category is auto-managed)."
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Contacts categorized',
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
