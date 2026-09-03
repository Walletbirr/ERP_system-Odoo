# Advanced Leave Management (Odoo 18 Community)

A replacement for the stock Time Off module, built around two constraints:
most employees have no Odoo login, and annual leave entitlement must grow
by a formula, not by manually created yearly milestone records.

## Install

1. Copy the `advanced_leave_management` folder into your addons path.
2. Update Apps list, then install "Advanced Leave Management".
3. Assign users to the security groups (Settings > Users):
   - **HR Officer** — enters/confirms leave directly, configures leave types
     and policies, manages allocations and opening-balance overrides.
   - **Leave Officer (Approver)** — flat pool that approves/refuses
     self-service requests. Add as many users as needed; any member can act
     on any pending request unless a Leave Type restricts approval to
     specific officers.
   - **Employee Self-Service** — only needed for the (optional) employees
     who have a login and submit their own requests.
4. On each employee record, set **Contract Start Date (for Leave Accrual)**.
   This is the anchor the accrual engine uses; if you use the Contracts
   module, sync this from the active contract (not wired up automatically
   here to avoid a hard dependency — see "Next Steps").
5. Configure your Leave Types (Leave Management > Configuration > Leave
   Types), picking a Balance Type for each: No Allocation, Fixed Quota, or
   Accrual Bank.

## How the two core problems are solved

**No system access required.** Every model keys off `hr.employee`, not
`res.users`. HR can create and confirm leave for any employee from the
backend with zero login requirement on the employee's part. Self-service
(`leave.request` submitted by an employee with a login) is a fully optional
second entry path, not the foundation.

**No manual yearly milestones.** `leave.type` accrual-bank fields
(`base_days`, `increment_per_year`, `increment_frequency_months`, `max_days`)
define a formula. The daily cron (`_cron_run_leave_accrual` on
`hr.employee`) walks forward from each employee's contract start date and
grants ledger entries automatically — no per-year record creation, ever,
for year 1 or year 50.

## Approval logic (origin-based, not access-based)

Whether a request needs approval is determined by **how it was entered**,
not by whether the employee has a login:

- `action_hr_confirm()` — HR enters/confirms leave directly. Sets state to
  `approved` immediately. No Leave Officer step is ever touched.
- `action_submit()` — used only by the self-service form. Sets state to
  `submitted` and notifies the Leave Officer pool. Only this path ever
  reaches `action_approve()` / `action_refuse()`.

This is enforced by the `origin` field, which is set by which action was
called, not inferred from the employee's access rights.

## Ledger-based balances (audit trail, not field overwrites)

`leave.allocation` holds one record per employee + leave type. Its
`current_balance` is always **computed** as the sum of `leave.ledger.line`
rows (accrual, opening_balance, deduction, reversal, manual_adjustment,
carry_over, expiry). Nothing ever silently overwrites a balance field.

**Migration:** call `allocation.action_set_opening_balance(amount,
effective_date, reason)` for employees who started before this module was
installed. This writes one auditable `opening_balance` ledger line for the
delta and moves `last_accrual_date` forward, so the cron computes all
future growth from the new baseline instead of the original contract date.
Use **Leave Management > Configuration > Import Opening Balances** to do
this in bulk from a `.xlsx`/`.csv` file (columns: Employee, Balance,
Effective Date, Reason) instead of one employee at a time.

## Leave Encashment (paying out unused leave)

**Leave Management > Leave Encashment > New.** Pick an employee and an
accrual-bank or fixed-quota leave type, enter the days to pay out and a
monthly basic salary (auto-filled from the employee's active contract wage
if the Contracts module is installed and one exists — always editable).
The daily rate is `basic_salary / days_in_month` (default 30, configurable
per company), and the amount is `daily_rate x days` — both editable before
posting in case the real-world number differs.

Clicking **Post**:
1. Validates there's enough balance to encash.
2. Creates and posts a two-line `account.move` (debit the configured
   Expense account, credit the configured Payable account) in the
   configured journal.
3. Deducts the days from the employee's leave ledger as an `encashment`
   move, linked back to this record for audit purposes.

**Before using this, configure the accounts:** Leave Management >
Configuration > Encashment Settings — set the Expense Account, Payable
Account, and Journal (all company-level, on `res.company`). Posting is
blocked with a clear error until these are set.

**Deliberately out of scope:** this does not recompute income tax or
payroll withholding on the encashed amount (as seen in manual payroll
worksheets that show "Previous Tax / New Tax / Tax Difference"). That is a
payroll tax engine problem, not a leave-balance problem — if you need it,
it belongs in a Payroll module integration that reads the posted
`leave.encashment` records, not in this module.

## What's implemented

- Employee-centric, login-optional data model
- Formula-based accrual engine with a daily cron, capped growth, and
  catch-up logic if the cron was inactive for a while
- Three balance behaviors per leave type: No Allocation / Fixed Quota /
  Accrual Bank
- Origin-based approval routing (HR entry vs. self-service), flat
  multi-member Leave Officer group, optional per-type officer restriction
- Ledger-based balances with full audit trail and migration-friendly
  opening-balance overrides, plus a bulk import wizard for migration day
- Leave encashment: converts unused days into a monetary amount and posts
  a real, configurable journal entry, with the ledger deduction and
  accounting entry created atomically
- Overlap prevention, calendar-aware duration (excludes weekends/holidays
  via the employee's `resource.calendar`), negative-balance guard,
  mandatory-attachment enforcement, minimum-notice enforcement
- Cancellation with automatic balance reversal (distinct from refusal)
- Smart button on the Employee form showing live balances
- Approvals inbox, "My Leaves", calendar view, and basic list/search views

## Not yet built / next steps

- **Carry-over / expiry automation.** The fields exist on `leave.type`
  (`carry_over_allowed`, `carry_over_max_days`, `carry_over_expiry_months`)
  but no scheduled job yet turns them into `carry_over`/`expiry` ledger
  lines at year-end. Needs a year-end cron per company.
- **Fixed-quota reset automation.** `quota_reset = 'yearly'` is declared
  but not yet wired to a cron that posts a `quota_reset` ledger line each
  January 1st (or company fiscal year start).
- **Reporting:** leave-liability valuation (balance x daily rate, for
  finance provisioning), department-level pivot, an "expiring soon" report.
- **Multi-company hardening:** most models have `company_id` but record
  rules don't yet filter by company; add if you run multiple legal entities.
- **Contract module integration:** `leave_contract_start_date` is a plain
  field so this module has no hard dependency on `hr_contract`. If you use
  Contracts, add a small `_compute` or `related` to sync it from the active
  contract's `date_start` automatically.
- **Encashment reversal UI.** Posted encashments must currently be reversed
  from the Accounting app directly (the module blocks deleting/cancelling
  a posted record and points you there) rather than having a one-click
  "reverse" button on the encashment record itself.
- **Payroll tax integration on encashment** — see above, intentionally out
  of scope for this module.
- **Approval delegation** (backup approver when all officers are
  unavailable) and **blackout periods / team capacity limits** were
  discussed as valuable but intentionally left out of this first version
  to keep the core model set manageable — good candidates for a v2 module
  that depends on this one.
