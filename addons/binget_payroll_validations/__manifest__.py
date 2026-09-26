# -*- coding: utf-8 -*-
{
    "name": "Binget Payroll Validations",
    "version": "18.0.1.0.0",
    "summary": "Payroll eligibility validations: no payslips for departed "
                "employees or expired contracts; contract readonly after "
                "running; simplified payslip form.",
    "description": """
Payroll Validations
====================
Kept as its own module, separate from `payroll` and the other custom
payroll addons, so these rules can be changed or removed without
touching any of them.

What this module does:
-----------------------
1. Blocks creating/computing a payslip for an employee whose leave_date
   falls before the payslip's period start (i.e. they had already left
   before this payslip's month even began).
2. Blocks creating/computing a payslip for an employee whose contract
   has already ended (contract_id.date_end) before the payslip's period
   start.
3. Locks hr.contract fields once the contract is in the 'open' (Running)
   state - stops accidental edits to a contract that's already active.
4. Hides the 'Worked Days & Inputs' tab on the payslip form (view-only
   change, nothing removed from the data model).

Left for a follow-up module / fix (documented, not silently ignored):
-----------------------------------------------------------------------
- The employee picker showing 'Administrator' - needs to be confirmed
  whether that dialog is even payroll's employee field before writing a
  domain for it.
- The Refund button's reported looping behaviour - needs to be
  reproduced and traced before being 'fixed', since we don't yet know
  the actual cause.
""",
    "author": "Binget",
    "license": "LGPL-3",
    "depends": ["payroll", "employee_profile_custom"],
    "data": [
        "views/hr_payslip_views.xml",
        "views/hr_payslip_employees_views.xml",
        "views/hr_contract_views.xml",
    ],
    "installable": True,
    "application": False,
}
