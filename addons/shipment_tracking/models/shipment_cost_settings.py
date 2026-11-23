# /custom_addons/shipment_tracking/models/shipment_cost_settings.py

from odoo import models, fields, api

CONFIG_PARAM = 'shipment_tracking.tax_account_id'


class ShipmentCostSettings(models.TransientModel):
    """
    Costs ▸ Configuration ▸ Tax Account Settings

    Lets an admin define one Tax Account that is automatically applied to
    every new Shipment Cost record, instead of every user having to pick
    it manually from the full Chart of Accounts each time.

    The value is stored as a single ir.config_parameter (no extra table,
    no changes to res.company). The Tax Account field on the Shipment
    Cost form is read-only — this screen is the single place to change it.
    """
    _name = 'shipment.cost.settings'
    _description = 'Shipment Cost Settings'

    tax_account_id = fields.Many2one(
        'account.account', string='Default Tax Account',
        domain="[('account_type', 'not in', ['asset_receivable', 'liability_payable'])]",
        help=(
            'This account is automatically set as the Tax Account on every new '
            'Shipment Cost record. The Tax Account field on Shipment Cost is '
            'read-only — update the default here to change it.'
        ),
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'tax_account_id' in fields_list:
            param = self.env['ir.config_parameter'].sudo().get_param(CONFIG_PARAM)
            res['tax_account_id'] = int(param) if param else False
        return res

    def action_save(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            CONFIG_PARAM, self.tax_account_id.id or '',
        )
        return {'type': 'ir.actions.act_window_close'}
