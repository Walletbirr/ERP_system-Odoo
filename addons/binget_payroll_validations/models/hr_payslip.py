# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # ------------------------------------------------------------------
    # Why a constraint instead of overriding compute_sheet/action_*:
    # we don't have confirmed method names for every entry point in the
    # base `payroll` module (New form, batch run, import, etc.), and a
    # constraint fires on create() AND write() no matter which of those
    # paths is used - so there's no path that can slip through by
    # calling a button method we didn't happen to override.
    # ------------------------------------------------------------------
    @api.constrains("employee_id", "contract_id", "date_from", "date_to")
    def _check_employee_payable(self):
        for slip in self:
            employee = slip.employee_id
            if not employee or not slip.date_from:
                continue

            # ---- Rule 1: employee already left before this period ----
            if employee.is_on_leave and employee.leave_date:
                if slip.date_from > employee.leave_date:
                    raise ValidationError(_(
                        "%(employee)s left the company on %(leave_date)s, "
                        "before this payslip's period (%(date_from)s). "
                        "A payslip cannot be created for a period after "
                        "the employee's leave date."
                    ) % {
                        "employee": employee.name,
                        "leave_date": employee.leave_date,
                        "date_from": slip.date_from,
                    })

            # ---- Rule 2: contract not Running (expired/cancelled/etc) ----
            contract = slip.contract_id
            if contract and contract.state != "open":
                raise ValidationError(_(
                    "%(employee)s's contract is not Running (status: "
                    "%(state)s). A payslip cannot be created against a "
                    "contract that isn't currently active."
                ) % {
                    "employee": employee.name,
                    "state": contract.state,
                })

            if contract and contract.date_end:
                if slip.date_from > contract.date_end:
                    raise ValidationError(_(
                        "%(employee)s's contract ended on %(date_end)s, "
                        "before this payslip's period (%(date_from)s). "
                        "A payslip cannot be created for a period after "
                        "the contract's end date."
                    ) % {
                        "employee": employee.name,
                        "date_end": contract.date_end,
                        "date_from": slip.date_from,
                    })

    # ------------------------------------------------------------------
    # Employee picker on the payslip form: exclude anyone who is on
    # leave with a leave_date already in the past relative to today.
    # This only narrows what's offered when creating a *new* payslip -
    # the constraint above is still the real enforcement, since a
    # domain alone can be bypassed (e.g. via an existing draft, an
    # import, or a saved filter).
    # ------------------------------------------------------------------
    @api.model
    def _get_payable_employee_domain(self):
        return [
            "|",
            ("is_on_leave", "=", False),
            ("leave_date", "=", False),
        ]
