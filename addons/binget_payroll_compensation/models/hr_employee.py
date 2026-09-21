# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # ------------------------------------------------------------------
    # Payroll: per-employee override of the Net Salary credit account.
    #
    # By default every payslip's Net Salary line is posted to whatever
    # account is set on the Net Salary rule itself (Payroll >
    # Configuration > Salary Rules > Net Salary > Accounting > Credit
    # Account - e.g. "101510 Binget Microfinance"). Some employees are
    # actually paid through a different bank, so this flags them; the
    # alternate account itself is configured once, company-wide, under
    # Payroll > Configuration (res.company.alternate_net_payment_account_id
    # - see models/res_company.py). See models/hr_payslip.py for where
    # this flag is actually applied when a payslip is posted.
    #
    # The field lives here (rather than in employee_profile_custom, which
    # only displays it on the profile UI) so it's always available
    # wherever hr.employee is used, regardless of which other HR modules
    # happen to be installed.
    # ------------------------------------------------------------------
    use_alternate_net_payment_account = fields.Boolean(
        string="Use Alternate Net Payment Account",
        help=(
            "If checked, this employee's Net Salary is posted to the "
            "Alternate Net Payment Account configured under Payroll > "
            "Configuration, instead of the Credit Account set on the Net "
            "Salary rule itself. Use this for employees paid through a "
            "different bank than the company default."
        ),
    )
