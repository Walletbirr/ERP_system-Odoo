from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    lc_default_fee_account_id = fields.Many2one(
        related='company_id.lc_default_fee_account_id',
        readonly=False,
        string="Default LC Fee Account"
    )
    lc_default_vat_account_id = fields.Many2one(
        related='company_id.lc_default_vat_account_id',
        readonly=False,
        string="Default LC VAT Account"
    )
    lc_default_accountant_id = fields.Many2one(
        related='company_id.lc_default_accountant_id',
        readonly=False,
        string="Default LC Accountant"
    )
