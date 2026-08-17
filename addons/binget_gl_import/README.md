# Binget GL Simple Import

Lets you use Odoo's normal Journal Entries "Load Data File" import with a raw
GL export (just Account, Description, Debit, Credit columns) - no manual
Excel restructuring needed.

## Install

1. Copy the `binget_gl_import` folder into your Odoo addons path.
2. Restart the Odoo service (or just refresh if running with `--dev=all`).
3. Apps > Update Apps List > search "Binget GL Simple Import" > Install.

## How it behaves

Go to **Accounting > Journal Entries > Import records** exactly as before.

- If your uploaded file has just Account/Description/Debit/Credit style
  columns (no Journal or Reference column), the module detects this and
  transforms it in the background before showing you the column-mapping
  screen: it groups everything into one entry, and shows you Journal /
  Date / Reference / Account / Label / Debit / Credit already filled in.
- If any account code in the file doesn't exist in your Chart of Accounts,
  the import stops right there with a list of the missing codes - nothing
  gets created in Odoo.
- If Debit and Credit totals don't match, the import stops with the
  difference shown.
- Journal is auto-set to your first "Miscellaneous Operations" type
  (`type = general`) journal. If none exists, you'll get a clear message
  asking you to create one.
- Reference auto-increments (JE-0001, JE-0002, ...) - only assigned once
  you actually click **Import** (not during Test/preview), so previewing
  a file repeatedly doesn't burn numbers.
- If your file is already in the full structured format (has its own
  Journal/Reference columns, like previously prepared files), the module
  leaves it untouched - imports normally, no change in behavior.

## Testing checklist

1. Try a small file (5-10 rows) with account codes that exist in your COA
   and that balance - should convert automatically and import cleanly.
2. Try a file with one deliberately wrong/non-existent account code -
   import should be blocked with that code listed, nothing created.
3. Try a file that doesn't balance - import should be blocked with the
   imbalance amount shown.
4. Try re-uploading the same clean file twice - Reference should
   increment (JE-0001 then JE-0002), not repeat or skip oddly.
5. Try uploading an already fully-structured file (Journal/Reference
   columns present) - should behave exactly like stock Odoo import,
   untouched.

## Notes / limitations

- Journal selection is automatic (first "Miscellaneous Operations" type
  journal). If you need to post to a different journal per import, this
  version doesn't have a way to choose it from the UI - let me know if
  that's needed and it can be added as a setting.
- Multi-company: the reference sequence is currently shared across all
  companies. Flag if you need it split per company.
- Account matching is by exact `code` match against `account.account`.
