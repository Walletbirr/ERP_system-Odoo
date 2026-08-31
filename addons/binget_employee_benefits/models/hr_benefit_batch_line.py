# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrBenefitBatchLine(models.Model):
    """One employee's resolved benefit amount for a batch period.
    Editable (amount / include) until posted; once a move_id is set the
    line is locked, matching how a posted payslip line is no longer
    editable.
    """

    _name = "hr.benefit.batch.line"
    _description = "Employee Benefits Batch Line"
    _order = "employee_id"

    batch_id = fields.Many2one(
        "hr.benefit.batch", required=True, ondelete="cascade", index=True
    )
    date_to = fields.Date(related="batch_id.date_to", store=True)
    company_id = fields.Many2one(related="batch_id.company_id", store=True)
    currency_id = fields.Many2one(related="batch_id.currency_id")
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    category_id = fields.Many2one("hr.benefit.category", required=True)
    benefit_line_id = fields.Many2one(
        "hr.employee.benefit.line",
        string="Source Benefit",
        help="The employee benefit configuration this line was computed from.",
    )
    amount = fields.Monetary(required=True)
    include = fields.Boolean(
        default=True,
        help="Uncheck to exclude this employee from this batch's posting "
        "(e.g. they left the company, or the card was not issued this "
        "period) without deleting the computed row.",
    )
    move_id = fields.Many2one("account.move", readonly=True, copy=False)
    state = fields.Selection(related="batch_id.state")

    def action_post_single(self):
        """Post just this one line as its own journal entry, independent
        of the rest of the batch. Journal comes from Account Configuration.
        """
        for line in self:
            if line.move_id:
                raise UserError(_("This line is already posted."))
            if not line.include:
                raise UserError(
                    _("This line is excluded - tick 'Include' before posting it.")
                )
            line._post_lines()

    def _post_lines(self, journal=None):
        """Create one account.move covering all lines in `self`, with a
        debit/credit pair per line using the company-wide Account
        Configuration accounts and journal, then post it and stamp
        move_id back onto each line.
        """
        lines = self.filtered(lambda l: not l.move_id)
        if not lines:
            return
        Config = self.env["hr.benefit.account.config"]
        by_company = {}
        for line in lines:
            by_company.setdefault(line.company_id, self.env["hr.benefit.batch.line"])
            by_company[line.company_id] |= line

        for company, company_lines in by_company.items():
            config = Config.get_for_company(company)
            if not config.debit_account_id or not config.credit_account_id:
                raise UserError(
                    _(
                        "Employee Benefits Account Configuration is incomplete "
                        "for %s. Set both Debit and Credit accounts under "
                        "Accounting > Employee Benefits > Account Configuration "
                        "before posting."
                    )
                    % company.name
                )

            move_journal = journal or config.journal_id
            if not move_journal:
                move_journal = self.env["account.journal"].search(
                    [("type", "=", "general"), ("company_id", "=", company.id)],
                    limit=1,
                )
            if not move_journal:
                raise UserError(
                    _(
                        "No journal is available to post these benefits for "
                        "%s. Set the Default Journal under Accounting > "
                        "Employee Benefits > Account Configuration."
                    )
                    % company.name
                )

            move_line_vals = []
            for line in company_lines:
                label = _("%(category)s - %(employee)s") % {
                    "category": line.category_id.name,
                    "employee": line.employee_id.name,
                }
                # Odoo 18: use work_contact_id (address_home_id was removed).
                partner = getattr(line.employee_id, "work_contact_id", False) or False
                partner_id = partner.id if partner else False
                move_line_vals.append(
                    (
                        0,
                        0,
                        {
                            "name": label,
                            "account_id": config.debit_account_id.id,
                            "partner_id": partner_id,
                            "debit": line.amount,
                            "credit": 0.0,
                        },
                    )
                )
                move_line_vals.append(
                    (
                        0,
                        0,
                        {
                            "name": label,
                            "account_id": config.credit_account_id.id,
                            "partner_id": partner_id,
                            "debit": 0.0,
                            "credit": line.amount,
                        },
                    )
                )

            move = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "journal_id": move_journal.id,
                    "date": company_lines[0].batch_id.date_to,
                    "ref": company_lines[0].batch_id.name,
                    "line_ids": move_line_vals,
                }
            )
            move.action_post()
            company_lines.write({"move_id": move.id})
