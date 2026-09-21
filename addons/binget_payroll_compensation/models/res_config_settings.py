# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    payroll_journal_id = fields.Many2one(
        related="company_id.payroll_journal_id",
        readonly=False,
        string="Default Salary Journal",
    )
    payroll_analytic_account_id = fields.Many2one(
        related="company_id.payroll_analytic_account_id",
        readonly=False,
        string="Default Payroll Analytic Account",
    )
    payroll_structure_id = fields.Many2one(
        related="company_id.payroll_structure_id",
        readonly=False,
        string="Default Salary Structure",
    )
    alternate_net_payment_account_id = fields.Many2one(
        related="company_id.alternate_net_payment_account_id",
        readonly=False,
        string="Alternate Net Payment Account",
    )
