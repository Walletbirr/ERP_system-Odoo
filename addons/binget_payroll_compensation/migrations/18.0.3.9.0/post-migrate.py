# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
#
# The payslip Salary Journal now comes only from Settings > Payroll >
# Salary Journal, not from the contract. Bring every payslip that is not
# Done yet in line with it, so old drafts stop showing a blank or stale
# journal. Done payslips keep the journal their entry was posted with.

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    slips = env["hr.payslip"].search([("state", "!=", "done")])
    for slip in slips:
        company = slip.company_id or slip.employee_id.company_id
        journal = company.payroll_journal_id
        if journal and slip.journal_id != journal:
            slip.journal_id = journal
