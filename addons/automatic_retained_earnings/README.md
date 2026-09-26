# Automatic Retained Earnings (Odoo 18 Community + Cybrosys Base Accounting Kit)

## Who does what (separation of duties)
- **Accounting Managers** (`account.group_account_manager`): configure the
  Retained Earnings account, closing journal, and auto-close behaviour via
  **Accounting > Retained Earnings Setup**. They're also the only ones who
  can reverse a posted closing.
- **Accountants** (`account.group_account_user`, includes Managers):
  create, compute, and post the actual year-end closing via
  **Accounting > Fiscal Year Closing**. They cannot delete a closing record
  or reverse one once posted - only a Manager can.
- Neither screen requires Settings/Company-admin access. Everything lives
  inside the Accounting module.

## What this module does
- Adds **one** new Chart-of-Accounts entry per company: an equity account
  called **"Retained Earnings"** (created automatically on install if you
  don't already have one; rename/recode it afterwards if you like).
- Everything else is already tracked by Odoo natively — every posted
  invoice, bill, and journal entry already hits your Income/Expense
  accounts. This module does **not** duplicate that tracking; it only adds
  the missing **year-end closing** step that Odoo Community doesn't do
  with real journal entries.
- **Accounting > Retained Earnings Setup** (Managers only): pick the
  Retained Earnings account, the closing journal, and whether closings
  should post automatically each year.
- **Accounting > Fiscal Year Closing** (Accountants + Managers):
  1. **Compute Balances** – sums every Income/Other Income/Expense/COGS/
     Depreciation account for the chosen date range.
  2. **Post Closing Entry** – asks for confirmation, then creates one
     balanced journal entry that debits every credit-balance (income)
     account and credits every debit-balance (expense) account back to
     zero, with the net difference (profit or loss) posted to Retained
     Earnings.
  3. **Reverse Closing** (Managers only) – if a period needs to be
     re-opened, this posts a clean reversal entry rather than deleting
     anything.
- Optional **scheduled action** (Settings > Technical > Automation >
  Scheduled Actions > "Retained Earnings: Auto-close Fiscal Year", runs
  daily) that automatically creates and posts the closing the day after
  each fiscal year ends — toggle it from Retained Earnings Setup.
- A period can never be closed twice: closing entries exclude their own
  lines from future runs, and there's a hard DB constraint of one closing
  per company per date range.

## Install
1. Copy `automatic_retained_earnings/` into your Odoo 18 `addons` path,
   alongside `base_accounting_kit`.
2. Update Apps list, then install **Automatic Retained Earnings**.
3. As an Accounting Manager, go to **Accounting > Retained Earnings
   Setup** and confirm the auto-created account and closing journal look
   right for your Chart of Accounts.

## Using it at year-end
1. Go to **Accounting > Fiscal Year Closing**.
2. Create a new record, set `Date From` / `Date To` for the fiscal year,
   confirm the journal and Retained Earnings account.
3. Click **Compute Balances** to preview every account that will be
   zeroed out and the resulting net profit/loss.
4. Click **Post Closing Entry** and confirm.
5. (Recommended) Set the company's **Fiscal Year Lock Date** to `Date To`
   afterwards (Accounting > Configuration > Settings > Lock Dates) so no
   one can post new entries into the closed year without unlocking it
   first — this module does not change lock dates for you.

## Auto-Post Date (optional)
If **Auto-Post Closing Entry Every Year** is enabled in Retained Earnings
Setup, two extra fields appear: **Auto-Post Month** and **Auto-Post Day**.
Together they're the one calendar date each year the scheduled action
checks for; when it hits that date it automatically closes the most
recently completed fiscal year. This is decoupled from your fiscal year
end date on purpose, so you can give yourself a grace period — e.g. fiscal
year ends Dec 31, but Auto-Post Date is set to Feb 15 to allow six weeks
for year-end adjustments before the books close automatically.

**Most companies should leave Auto-Post off** and close deliberately each
year from **Accounting > Fiscal Year Closing** after review — that screen
is the manual trigger point, and posting there always requires an
explicit confirmation click.

## Menu placement
`views/menu_views.xml` hooks both menus into `account.menu_finance` (the
Accounting app root) to avoid guessing a deeper submenu id that Base
Accounting Kit may have restructured on your build (guessing wrong is
exactly what broke the first version of this module against your
"Binget" Accounting settings page). Once installed, drag either menu
into a deeper submenu — e.g. next to the existing "Year-End Closing"
flyout — from **Settings > Technical > Menus**; that's a safe UI action
since it doesn't touch a view's internal structure.

## Important notes / things to verify in your environment before go-live
- **account_type values**: this module targets Odoo 18's standard P&L
  account types (`income`, `income_other`, `expense`,
  `expense_depreciation`, `expense_direct_cost`). If Base Accounting Kit
  or a localization module you have installed adds custom account types
  that should also be swept into the closing, add them to
  `PL_ACCOUNT_TYPES` in `models/account_fiscalyear_closing.py`.
- **account.account company field**: Odoo 18 changed multi-company
  handling for the Chart of Accounts more than once across minor
  versions. `hooks.py` auto-detects whether your instance uses
  `company_id` or `company_ids` on `account.account`, but please install
  on a staging copy first and confirm the Retained Earnings account gets
  created correctly for each company.
- This module deliberately does **not** touch Odoo's built-in "Unaffected
  Earnings"/`equity_unaffected` automatic P&L rollup used in the Balance
  Sheet report — it posts to a normal `equity` account instead, so there's
  no double counting: once a year is closed, its P&L accounts are at
  zero, and the built-in rollup for that year is correspondingly zero too.

## Testing checklist before first real year-end run
1. Duplicate your database to a staging environment.
2. Post a handful of test invoices/bills in a past period.
3. Run a closing for that period and confirm:
   - Total Income / Total Expense / Net Result match your P&L report.
   - The generated journal entry balances to zero.
   - Income/Expense accounts show a zero balance for that period after
     posting (check via Accounting > Reporting > General Ledger filtered
     to the period).
   - Retained Earnings account balance equals the net result.
4. Test **Reverse Closing** (as a Manager) and confirm the P&L accounts
   reopen correctly.
