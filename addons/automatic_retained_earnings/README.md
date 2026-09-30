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
  Retained Earnings account and the closing journal.
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
2. Create a new record and pick the **Fiscal Year** (Date From / Date To fill
   in automatically; choose **Custom Range** to type your own dates), then
   confirm the journal and Retained Earnings account. Only entries dated
   inside the period are counted - anything dated after Date To is ignored.
3. Click **Compute Balances** to preview every account that will be
   zeroed out and the resulting net profit/loss.
4. Click **Post Closing Entry** and confirm.
5. (Recommended) Set the company's **Fiscal Year Lock Date** to `Date To`
   afterwards (Accounting > Configuration > Settings > Lock Dates) so no
   one can post new entries into the closed year without unlocking it
   first — this module does not change lock dates for you.

## Closing is always manual
The year is only ever closed by an accountant, from **Accounting > Fiscal
Year Closing**, after reviewing the figures. Posting always requires an
explicit confirmation click; there is no scheduled/automatic closing.

## Menu placement
On every install **and upgrade**, `_place_menus` (called from
`views/menu_views.xml`) nests *Retained Earnings Setup* under the Accounting
app's **Configuration** submenu and *Fiscal Year Closing* under its
**Accounting** submenu, finding those submenus by name rather than guessing
an xmlid. If a submenu isn't found, the item simply stays directly under the
Accounting app root.

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
