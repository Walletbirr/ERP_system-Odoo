{
    'name': 'Advanced Leave Management',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Management-driven leave management: no-login-required leaves, '
                'formula-based accrual, role-based approval, and per-type balance rules.',
    'description': """
Advanced Leave Management
==========================
A replacement for the stock Time Off module built for organizations where:

* Most employees do NOT have Odoo user accounts. HR enters and manages leave
  for everyone directly on the Employee record; nothing requires a login.
* Annual leave entitlement grows by a formula (base + years_of_service x
  increment, capped), computed from each employee's contract start date -
  not by manually created yearly "milestone" records.
* Employees who DO have a login can submit self-service requests, which are
  routed to a flat pool of Leave Officers (a role, not an org-chart manager)
  for approval. HR-entered leave never needs approval - HR's action IS the
  approval.
* Each Leave Type declares its own balance behavior: No Allocation
  (unpaid/unlimited), Fixed Quota (non-accruing, e.g. sick/marriage leave),
  or Accrual Bank (annual leave, ledger-based).

Key features
------------
* Employee-centric, login-optional data model.
* Ledger-based balances (leave.ledger.line) - every accrual, deduction,
  manual adjustment, carry-over and expiry is an auditable line, never a
  silent field overwrite.
* Migration-friendly opening balance overrides that the accrual engine
  picks up as the new baseline going forward.
* Flat, multi-member Leave Officer approval group, decoupled from the
  manager/org chart.
* Smart button on Employee showing live leave balances per type.
* Overlap prevention, calendar-aware duration, negative-balance guard,
  cancellation-with-reversal.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['hr', 'hr_contract', 'mail', 'account', 'payroll'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/sequence_data.xml',
        'data/tax_bracket_data.xml',
        'data/leave_type_data.xml',
        'views/leave_type_views.xml',
        'views/leave_request_views.xml',
        'views/leave_allocation_views.xml',
        'views/hr_employee_views.xml',
        'views/leave_opening_balance_import_views.xml',
        'views/leave_encashment_views.xml',
        'views/leave_tax_bracket_views.xml',
        'views/leave_menus.xml',
    ],
    'installable': True,
    'application': True,
}
