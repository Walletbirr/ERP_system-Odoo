# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    loan_account_id = fields.Many2one(
        related='company_id.loan_account_id', readonly=False)
    loan_journal_id = fields.Many2one(
        related='company_id.loan_journal_id', readonly=False)
