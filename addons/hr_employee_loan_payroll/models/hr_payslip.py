# -*- coding: utf-8 -*-
import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

LOAN_RULE_CODE = 'LOAN_DED'


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # ------------------------------------------------------------------
    # 1. Compute: split the LOAN_DED line into one line per loan installment
    # ------------------------------------------------------------------
    def get_lines_dict(self):
        lines_dict = super().get_lines_dict()
        for payslip in self:
            payslip._split_loan_lines(lines_dict)
        return lines_dict

    def _split_loan_lines(self, lines_dict):
        """The LOAN_DED rule returns the total of the due installments. Replace
        its single line by one line per installment so each one can be posted
        to its own loan receivable account and be marked paid individually."""
        self.ensure_one()
        keys = [k for k, v in lines_dict.items() if v.get('code') == LOAN_RULE_CODE]
        if not keys:
            return
        installments = self.employee_id.sudo()._get_loan_deduction_lines(
            self.date_from, self.date_to)
        currency = self.company_id.currency_id or self.env.company.currency_id
        for key in keys:
            vals = lines_dict[key]
            expected = sum(installments.mapped('amount'))
            # Only split when the rule amount is exactly the due installments
            # (a custom rule that caps/changes the amount is left untouched and
            # will be refused at confirmation, see _loan_check_lines).
            if not installments or currency.compare_amounts(abs(vals['total']), expected) != 0:
                continue
            del lines_dict[key]
            for inst in installments:
                new = dict(vals)
                amount = -inst.amount
                new.update({
                    'name': _("Loan %(loan)s - installment %(n)s of %(t)s",
                              loan=inst.loan_id.name, n=inst.sequence,
                              t=inst.loan_id.installment_count),
                    'amount': amount,
                    'quantity': 1.0,
                    'rate': 100.0,
                    'total': amount,
                    'loan_line_id': inst.id,
                })
                lines_dict['%s-%s' % (key, inst.id)] = new

    # ------------------------------------------------------------------
    # 2. Accounting: credit each loan's own receivable account
    # ------------------------------------------------------------------
    def _loan_account(self, line, account_id):
        if line.loan_line_id:
            loan = line.loan_line_id.loan_id
            if not loan.loan_account_id:
                raise UserError(_("Loan %s has no Loan Receivable Account.") % loan.name)
            return loan.loan_account_id.id
        return account_id

    def _prepare_debit_line(self, line, amount, date, debit_account_id, move_line_analytic_ids):
        return super()._prepare_debit_line(
            line, amount, date, self._loan_account(line, debit_account_id),
            move_line_analytic_ids)

    def _prepare_credit_line(self, line, amount, date, credit_account_id, move_line_analytic_ids):
        return super()._prepare_credit_line(
            line, amount, date, self._loan_account(line, credit_account_id),
            move_line_analytic_ids)

    # ------------------------------------------------------------------
    # 3. Confirm / cancel: keep the repayment schedule in sync
    # ------------------------------------------------------------------
    def _loan_check_lines(self):
        for slip in self:
            bad = slip.line_ids.filtered(
                lambda l: l.code == LOAN_RULE_CODE and not l.loan_line_id and l.total)
            if bad:
                raise UserError(_(
                    "The loan deduction on %s is not linked to any loan installment. "
                    "The LOAN_DED rule must return exactly the due installments "
                    "(use employee.get_loan_deduction_amount) - recompute the payslip.")
                    % slip.number)

    def action_payslip_done(self):
        # Core recomputes the sheet inside super(); validate afterwards but
        # before anything is marked paid. A failure rolls the whole confirm back.
        res = super().action_payslip_done()
        self._loan_check_lines()
        for slip in self:
            slip._loan_on_done()
        return res

    def _loan_on_done(self):
        self.ensure_one()
        loan_lines = self.line_ids.loan_line_id.sudo()
        if self.credit_note:
            # Refund of a validated payslip: the installments go back to pending.
            loan_lines._revert_paid()
            return
        # _mark_paid refuses a non-pending installment, which also protects
        # against two payslips deducting the same installment.
        loan_lines._mark_paid(self.date_to, self.number)
        self._loan_skip_held()

    def _loan_skip_held(self):
        """A due installment that was NOT deducted because the loan (or all
        loans) is on hold is skipped: the schedule gets one month longer."""
        self.ensure_one()
        picked = self.line_ids.loan_line_id.loan_id
        loans = self.env['hr.loan'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'running'),
        ]) - picked
        for loan in loans:
            reason = loan._get_hold_reason()
            if not reason:
                continue
            nxt = loan.line_ids.filtered(lambda l: l.state == 'pending').sorted('sequence')[:1]
            if not nxt or nxt.due_date > self.date_to:
                continue
            nxt._do_skip(note=reason, pause_log=loan._get_open_pause_log(),
                         reference=self.number)

    def action_payslip_cancel(self):
        done = self.filtered(lambda s: s.state == 'done' and not s.credit_note)
        res = super().action_payslip_cancel()
        for slip in done:
            slip.line_ids.loan_line_id.sudo()._revert_paid()
            self.env['hr.loan.line'].sudo().search([
                ('state', '=', 'skipped'),
                ('payment_reference', '=', slip.number),
                ('loan_id.employee_id', '=', slip.employee_id.id),
            ])._undo_skip()
        return res
