# Part of Binget Holding customizations. See LICENSE file for details.

{
    "name": "Payroll - Always Hide Invisible Lines",
    "version": "18.0.1.0.0",
    "category": "Payroll",
    "summary": "Always hide non-payslip and child rule lines from the "
    "Salary Computation tab, instead of relying on per-payslip toggles.",
    "description": """
Makes the 'Show only lines that appear on payslip' and 'Hide Child Lines'
behaviours permanent.

The OCA `payroll` module lets each payslip's Salary Computation tab show
every computed rule (including rules with 'Appears on Payslip' unchecked,
and child rule lines) unless a user manually enables the
'hide_invisible_lines' / 'hide_child_lines' toggles on that specific
payslip.

This module forces both filters to always apply, and hides the now
redundant toggles from the form view. The 'Appears on Payslip' checkbox on
each Salary Rule remains the single place that controls line visibility.
""",
    "license": "LGPL-3",
    "author": "Binget Holding",
    "depends": [
        "payroll",
    ],
    "data": [
        "views/hr_payslip_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
