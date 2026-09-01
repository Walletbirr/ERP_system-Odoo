# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
#
# One-time cleanup for the root cause behind the all-zero rows in the
# August payroll summary: any contract created before the company-wide
# Salary Journal / Salary Structure / Analytic Account were configured in
# Settings never got those fields filled in, and nothing ever went back
# to fix them - so every payslip generated from them computed nothing.
#
# This runs the exact same fallback logic hr.contract already uses on
# create/onchange (_binget_apply_company_defaults), but applies it once
# to every contract that's still missing a value, regardless of when it
# was created. It never overwrites a contract that already has its own
# value set - only fills in what's genuinely blank.

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    contracts = env["hr.contract"].search(
        [
            "|",
            "|",
            ("struct_id", "=", False),
            ("journal_id", "=", False),
            ("analytic_account_id", "=", False),
        ]
    )
    contracts._binget_apply_company_defaults()
