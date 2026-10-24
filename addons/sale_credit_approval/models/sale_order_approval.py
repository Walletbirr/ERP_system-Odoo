# -*- coding: utf-8 -*-
from odoo import models, fields


class SaleOrderApproval(models.Model):
    _name = 'sale.order.approval'
    _description = 'Sales Order Approval Step'
    _order = 'sequence, id'

    sale_order_id = fields.Many2one(
        'sale.order', string='Sales Order', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(default=10)
    role = fields.Selection(
        [
            ('sales', 'Sales'),
            ('accounting', 'Accounting'),
            ('high_level_manager', 'High-Level Manager'),
        ],
        required=True,
        string='Role',
    )
    user_id = fields.Many2one('res.users', string='Approver')
    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        default='pending',
        required=True,
        string='Status',
    )
    date = fields.Datetime(string='Action Date')
    note = fields.Char(string='Note')
