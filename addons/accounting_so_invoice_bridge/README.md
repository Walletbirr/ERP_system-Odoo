# Accounting - Create Invoice from Sales Order

## What changed in this version (v18.0.4.0.0)

Previous versions checked `account.group_account_invoice` /
`account.group_account_user` (Odoo's native "Invoicing" field on the Users
form) to decide who could see the "Create Invoice" button on a Sales
Order. That turned out to be the wrong thing to gate on:

- On some instances, the native Invoicing field can't be left blank for a
  Sales user (something else forces a value into it) - so the button kept
  showing for a Sales user even though the view said it shouldn't.
- Even where it can be left blank, setting that field to anything hands
  the user the **entire Accounting/Invoicing app** (create invoices from
  scratch, register payments, etc.) - a much bigger hole than one button.

## The fix

A brand-new, dedicated permission group was added:
**"Can Create Invoice from Sales Order"**, living in its own category
**"Sales Order Invoicing (Custom)"**. It is completely independent of the
native Invoicing field.

- The button's visibility (`can_create_invoice` computed field, plus the
  view's `groups` attribute) now checks ONLY this new group, or Settings
  Administrator (`base.group_system`).
- A user's native Invoicing field can say "Billing", "Accountant", or
  nothing at all - it has zero effect on the button anymore.
- The only way to turn the button on for someone is for the admin to tick
  the new group explicitly.

## Setup after installing/upgrading

1. Settings > Users & Companies > Users > open the real accountant's
   record (e.g. Million).
2. Access Rights tab > find the new section **"Sales Order Invoicing
   (Custom)"** > tick **"Can Create Invoice from Sales Order"**.
3. Save. Hard-refresh the browser tab that has the Sales Order open.
4. Their native "Invoicing" field can be left however it needs to be for
   other reasons (or blank) - it no longer affects this button either way.

For a Sales user or Sales Administrator who should NEVER see the button:
simply never tick that box for them. No other configuration is needed;
the button stays hidden regardless of anything else on their user record.

## Previously fixed (still in place)

- **"To Invoice" list**: only shows confirmed orders (`state = 'sale'`)
  that still have something left to invoice
  (`invoice_status = 'to invoice'`). A fully invoiced order drops off
  immediately and for good - this list is a worklist, not a history log.
- **List footer dash row**: removed by explicitly setting `sum=""` on the
  Total column, which overrides Odoo's automatic footer aggregation.

## Install / Upgrade

Replace the old module folder entirely with this one, then in Odoo:
Apps > (remove the "Apps" filter, search the module) > Upgrade.
