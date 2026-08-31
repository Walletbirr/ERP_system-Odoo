from odoo import models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # --------------------------------------------------------------
    # Standard OCA payroll_account decides debit-vs-credit using the
    # SIGN of the rule's computed amount, no matter which field
    # (Debit Account / Credit Account) the account was placed in on
    # the salary rule. That means a "Debit Account" can silently end
    # up posting as a credit line, which is very confusing to anyone
    # configuring rules without knowing that internal behaviour.
    #
    # Binget's convention instead is: the field you fill in on the
    # rule IS the side it posts to. Always. No exceptions, no sign
    # logic. This override makes that literal.
    # --------------------------------------------------------------

    def _prepare_debit_line(
        self, line, amount, date, debit_account_id, move_line_analytic_ids
    ):
        vals = super()._prepare_debit_line(
            line, amount, date, debit_account_id, move_line_analytic_ids
        )
        vals["debit"] = abs(amount)
        vals["credit"] = 0.0
        return vals

    def _prepare_credit_line(
        self, line, amount, date, credit_account_id, move_line_analytic_ids
    ):
        vals = super()._prepare_credit_line(
            line, amount, date, credit_account_id, move_line_analytic_ids
        )
        vals["debit"] = 0.0
        vals["credit"] = abs(amount)
        return vals
