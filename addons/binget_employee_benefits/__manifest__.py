# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
{
    "name": "Employee Benefits (Non-Payroll)",
    "summary": "Track company-provided employee benefits (mobile/airtime cards, "
    "and similar non-cash benefits) completely outside payroll, with "
    "HR-owned benefit categories, Accounting-owned GL accounts, and a "
    "compute/post workflow for one employee or everyone at once.",
    "description": """
Employee Benefits (Non-Payroll)
================================

Purpose
-------
Some employee benefits (e.g. a company-issued mobile/airtime card) are a
real accounting cost, attributable to a specific employee, but are
deliberately NOT part of salary/payroll computation. This module tracks
those benefits completely outside `hr.salary.rule` / payroll structures,
while still giving Accounting a clean way to see every employee's benefit
amount at once and post it to the correct GL accounts each month.

Design
------
* HR owns the Benefit Category master data (Employees > Configuration >
  Benefit Categories) - HR creates each category (e.g. "Card Allowance")
  and its own dropdown of values (e.g. 100, 200, 500, "Unlimited"). HR
  then assigns a category + value to each employee directly on the
  Employee form's Benefits tab - no amount is ever typed by hand, and
  nothing entered here can affect a payslip.
* A "Label" value (e.g. "Unlimited") is not a number itself, so it has
  its own dated rate history instead of a single amount - so a rate
  change this year never rewrites what a past period already posted.
* Accounting configures Debit/Credit accounts and a default journal once
  for all categories (Accounting > Employee Benefits > Account
  Configuration). There is a single shared configuration, not per-category.
* Accounting > Employee Benefits has three menu items only:
  - Single Employee: compute and post just one employee's benefits
    (Monthly or Yearly period).
  - All Employees: list of past runs; use the Generate button (modal) to
    start a new run for all employees or a selected subset / department.
  - Account Configuration: the single shared debit, credit, and journal.
* A category is Monthly or Yearly - a Monthly batch only pulls Monthly
  categories, a Yearly batch only pulls Yearly ones.

This module has no dependency on any payroll module and never writes to
any payroll model - the separation is structural, not just procedural.
""",
    "version": "18.0.1.1.0",
    "category": "Human Resources",
    "author": "Binget Holding",
    "license": "AGPL-3",
    "depends": ["hr", "account"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_benefit_category_views.xml",
        "views/hr_employee_benefit_line_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_benefit_batch_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
