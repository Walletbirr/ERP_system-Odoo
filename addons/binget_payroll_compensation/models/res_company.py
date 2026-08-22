# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    payroll_journal_id = fields.Many2one(
        "account.journal",
        string="Default Salary Journal",
        help=(
            "Single company-wide journal used to post every payslip's "
            "accounting entry. Set this once here instead of on every "
            "individual contract - if the company ever changes journal, "
            "update it in one place and every future payslip picks it up."
        ),
    )
    payroll_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Default Payroll Analytic Account",
        help=(
            "Fallback cost-center account used for payroll postings when "
            "an employee's department has no analytic account of its own "
            "set. Department-level analytic accounts, when present, take "
            "priority over this default."
        ),
    )
    payroll_structure_id = fields.Many2one(
        "hr.payroll.structure",
        string="Default Salary Structure",
        help=(
            "Single company-wide salary structure applied to every new "
            "contract, since every employee shares the same rule set - "
            "only the underlying data (wage, allowances) varies per "
            "person. Set this once here instead of picking a structure "
            "for every contract individually."
        ),
    )
