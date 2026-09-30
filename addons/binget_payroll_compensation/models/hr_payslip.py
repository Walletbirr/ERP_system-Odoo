# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # ------------------------------------------------------------------
    # Salary Journal on the payslip: ONE journal for everybody, taken from
    # Settings > Payroll > Salary Journal (res.company.payroll_journal_id).
    #
    # payroll_account defines this field as a related copy of
    # contract_id.journal_id, so a payslip depended on its contract
    # having a journal - and showed "Invalid fields: Salary Journal" when
    # the contract was blank or had none, even with Settings configured.
    # The contract is no longer consulted at all. Change the journal in
    # Settings and every payslip that is not Done yet follows it. A Done
    # payslip keeps the journal its accounting entry was posted with.
    # ------------------------------------------------------------------
    journal_id = fields.Many2one(
        "account.journal",
        string="Salary Journal",
        related=False,
        compute="_compute_journal_id_binget",
        store=True,
        readonly=True,
    )

    @api.depends("company_id.payroll_journal_id", "employee_id.company_id")
    def _compute_journal_id_binget(self):
        for slip in self:
            if slip.state == "done" and slip.journal_id:
                continue
            company = slip.company_id or slip.employee_id.company_id
            slip.journal_id = company.payroll_journal_id or slip.journal_id

    @api.onchange("contract_id")
    def onchange_contract(self):
        # payroll_account copies the contract's journal here; put the
        # Settings journal back so the contract never decides it.
        res = super().onchange_contract()
        self._compute_journal_id_binget()
        return res

    # ------------------------------------------------------------------
    # Per-employee override of the Net Salary Credit Account.
    #
    # payroll_account's action_payslip_done() builds every journal item's
    # account straight from the salary rule's own static Credit Account /
    # Debit Account fields (Payroll > Configuration > Salary Rules), so
    # by default every employee's Net Salary posts to the same account
    # (e.g. "101510 Binget Microfinance").
    #
    # Some employees are actually paid through a different bank. Those
    # employees are flagged on their profile via the "Use Alternate Net
    # Payment Account" checkbox (hr.employee.use_alternate_net_payment_account,
    # defined in employee_profile_custom), and the alternate account
    # itself is configured once, company-wide, under Payroll >
    # Configuration (res.company.alternate_net_payment_account_id,
    # defined alongside this).
    #
    # payroll_account resolves the credit account with a single inline
    # field read inside action_payslip_done, not through any overridable
    # helper method, so there is no clean extension point to change the
    # account *before* the journal entry is created. Instead, this runs
    # straight after payroll_account has done its normal posting (super())
    # and, only for flagged employees, swaps the already-created Net
    # Salary journal item over to the alternate account. Odoo doesn't
    # allow editing the account of an already-posted journal item, so the
    # move is briefly reset to draft and re-posted around that one write.
    # ------------------------------------------------------------------
    def action_payslip_done(self):
        res = super().action_payslip_done()
        for slip in self:
            slip._apply_alternate_net_payment_account()
        return res

    def _apply_alternate_net_payment_account(self):
        self.ensure_one()
        if not self.employee_id.use_alternate_net_payment_account:
            return
        if not self.move_id:
            return

        alt_account = self.company_id.alternate_net_payment_account_id
        if not alt_account:
            _logger.warning(
                "Payslip %s: employee %s is flagged to use an alternate "
                "Net Payment Account, but none is configured under "
                "Payroll > Configuration - Net Salary was posted to the "
                "default account instead.",
                self.number,
                self.employee_id.name,
            )
            return

        net_line = self.line_ids.filtered(lambda line: line.code == "NET")
        if not net_line:
            return

        default_account = net_line[:1].salary_rule_id.account_credit
        if not default_account or default_account == alt_account:
            # Nothing to move - either the rule has no Credit Account at
            # all, or it already points at the alternate account.
            return

        currency = self.company_id.currency_id
        target_amount = currency.round(
            -net_line[:1].total if self.credit_note else net_line[:1].total
        )

        candidate_lines = self.move_id.line_ids.filtered(
            lambda ml: ml.account_id == default_account
            and currency.compare_amounts(ml.credit - ml.debit, target_amount) == 0
        )
        if len(candidate_lines) != 1:
            # Ambiguous (0 or several equally-matching journal items) -
            # safer to leave the entry untouched than guess wrong.
            _logger.warning(
                "Payslip %s: could not uniquely identify the Net Salary "
                "journal item to switch to the alternate payment account "
                "(%d candidate(s) found on account %s) - left unchanged. "
                "Please review/adjust the journal entry manually.",
                self.number,
                len(candidate_lines),
                default_account.display_name,
            )
            return

        move = self.move_id
        if move.journal_id.restrict_mode_hash_table:
            # Secured/inalterable entries can't be reset to draft - leave
            # it for manual correction rather than raising here.
            _logger.warning(
                "Payslip %s: its journal (%s) uses secured/inalterable "
                "entries, so the Net Salary journal item can't be "
                "switched to the alternate payment account automatically. "
                "Please adjust it manually if needed.",
                self.number,
                move.journal_id.name,
            )
            return

        was_posted = move.state == "posted"
        if was_posted:
            move.button_draft()
        candidate_lines.write({"account_id": alt_account.id})
        if was_posted:
            move.action_post()
