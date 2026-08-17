# -*- coding: utf-8 -*-
from odoo import models, fields, api


class BhApprovalConfig(models.Model):
    _name = 'bh.approval.config'
    _description = 'BH Sales Credit-Approval Configuration'
    _rec_name = 'name'

    name = fields.Char(default='Sales Approval Settings', required=True)
    high_level_manager_id = fields.Many2one(
        'res.users',
        string='High-Level Manager',
        help="Sales Orders that require credit approval (payment terms "
             "flagged 'Requires High-Level Manager Approval') are routed "
             "to this user. Only this user can approve or reject those "
             "orders.",
    )

    @api.model
    def get_config(self):
        """Return the single configuration record, creating it if missing."""
        config = self.search([], limit=1)
        if not config:
            config = self.create({})
        return config
