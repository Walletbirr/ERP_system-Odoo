# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrBenefitAccountConfig(models.Model):
    """Singleton (one row per company) holding the default GL accounts and
    journal used when posting any employee benefit. Accounting configures
    these once; they apply to every benefit category.
    """

    _name = "hr.benefit.account.config"
    _description = "Employee Benefits Account Configuration"
    _rec_name = "company_id"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        ondelete="cascade",
    )
    debit_account_id = fields.Many2one(
        "account.account",
        string="Debit Account (Expense)",
        domain="[('company_ids', 'in', company_id), ('deprecated', '=', False)]",
        help="Account debited when any employee benefit is posted "
        "(e.g. a Benefits / Communication expense account).",
    )
    credit_account_id = fields.Many2one(
        "account.account",
        string="Credit Account (Payable)",
        domain="[('company_ids', 'in', company_id), ('deprecated', '=', False)]",
        help="Account credited when any employee benefit is posted "
        "(e.g. a payable/liability or bank account, depending on settlement).",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Default Journal",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help="Default journal used when posting benefits if the batch "
        "itself does not specify one.",
    )

    _sql_constraints = [
        (
            "company_uniq",
            "unique(company_id)",
            "Only one Account Configuration is allowed per company.",
        ),
    ]

    @api.constrains("debit_account_id", "credit_account_id")
    def _check_distinct_accounts(self):
        for rec in self:
            if (
                rec.debit_account_id
                and rec.credit_account_id
                and rec.debit_account_id == rec.credit_account_id
            ):
                raise ValidationError(
                    "The Debit and Credit accounts must be different."
                )

    @api.model
    def get_for_company(self, company=None):
        """Return the config row for the given company (creating an empty
        one if none exists yet). Safe to call from posting logic.
        """
        company = company or self.env.company
        config = self.search([("company_id", "=", company.id)], limit=1)
        if not config:
            config = self.create({"company_id": company.id})
        return config
