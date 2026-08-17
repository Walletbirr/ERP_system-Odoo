# Accounting - Create Invoice from Sales Order

## What changed in this version (v18.0.13.0.0) - the File column, properly fixed

The previous attempt (forcing `bin_size: False` on the field) turned out
not to be enough - Odoo's list views still fetch binary fields in
"size only" mode at a level that per-field context can't override, so
Accounting's read-only row kept showing "1.05 Mb" with no way to
download.

This version stops relying on the standard Binary widget's read-only
rendering entirely. There's now a dedicated `download_link` field
(computed server-side, a plain safe HTML anchor with a download icon +
the real filename) that's used for the "File" column instead:

- **Accounting** always sees `download_link` - a real, working,
  click-to-download filename link, correct on first load, every time.
- **Sales** keeps the actual upload control (the standard Binary
  field) in that same column position, since they need to attach or
  replace a file, not just view one - this was already confirmed
  working on their side.

Only one "File" column ever renders per user (the two are mutually
exclusive via `column_invisible`, so there's no risk of two "File"
headers showing side by side).

Note on the "no payment proof submitted yet" notice: it's deliberately
Accounting/Admin-only. Salespeople never see the "Create Invoice"
button in the first place, so a reminder tied to that button wouldn't
mean anything on their side.

## What changed in v18.0.12.0.0

**Two UI fixes on the Payment Proofs tab, no permission/logic changes:**

- **File column was showing a size ("1.05 Mb") instead of the filename**
  for Accounting's read-only view. This is a known Odoo quirk: list
  views normally fetch binary fields in a bandwidth-saving "size only"
  mode, and the read-only rendering of the field falls back to
  displaying that size text when it can't resolve the real filename.
  The list now forces the actual file content to load for this field
  (`context="{'bin_size': False}"`), which fixes the filename +
  download-icon display for BOTH Accounting (read-only) and Sales
  (editable) consistently, without needing to hover or click into the
  row first. The same fix is applied to the header stat button's quick
  popup.
- **"No payment proof submitted yet" notice moved.** It used to sit
  immediately after "Create Invoice", crowding the button row. It now
  appears after "Cancel" (the last button in that row), with a bit of
  left spacing, read as a status note about the order rather than a
  label stuck on one button.

## What changed in v18.0.11.0.0 - important fix

**"Create Invoice" was still reachable by a Sales user, and their file
upload was locked - both from the same cause.**

Up to v18.0.9.0.0, the module still treated Odoo's native Invoicing
field (Settings > Users > that user > Access Rights tab > Invoicing:
Billing/Accountant) as an automatic, second way into accounting-level
access - on top of the dedicated "Can Create Invoice from Sales Order"
group. If that native field was set on a Sales user for any reason
(unrelated legacy data, a copy-pasted user template, etc.), it quietly:

- showed them the "Create Invoice" button, even though they only held
  a Sales role, **and**
- forced their own Payment Proof rows into read-only, since the same
  native field also drove the "always read-only for accounting"
  branch - blocking them from ever attaching a file.

**The fix:** both checks now look ONLY at the dedicated "Can Create
Invoice from Sales Order" group (or Settings Administrator). Odoo's
native Invoicing field has zero effect anywhere in this module now -
neither for the button nor for Payment Proof editability. This is the
single source of truth going forward.

### What to check after upgrading
- If a Sales user was still seeing "Create Invoice" before this
  update, it's worth opening Settings > Users & Companies > Users >
  that user > Access Rights tab and clearing/reviewing their
  "Invoicing" field - it no longer grants anything in this module, but
  it may still be worth tidying up so it doesn't cause confusion in
  the native Accounting/Invoicing app itself.
- Make sure every real accountant who should see "Create Invoice" has
  the dedicated group ticked: Access Rights tab > "Sales Order
  Invoicing (Custom)" section > "Can Create Invoice from Sales Order".
  This is now the ONLY way (besides Settings Administrator) to get
  that button - nothing happens automatically anymore.

## What changed in v18.0.10.0.0

**Smoother Payment Proof flow - no logic changes, just easier to see.**

- A new **stat button** ("Payment Proof") now sits in the Sales Order
  header, next to the other smart buttons, for anyone who already sees
  the Payment Proofs tab (Sales, Accounting, Admins). It shows one of
  three colour-coded states at a glance - green "Submitted", orange
  "Pending", grey "Not Uploaded" - so nobody has to open the tab just
  to check.
- Clicking that button pops up a quick, read-only list of every proof
  file on the order (with download), without leaving the order form.
- If an accountant has the "Create Invoice" button available but no
  proof has been Submitted yet, a small non-blocking warning now shows
  right next to the button as a heads-up. It's just a nudge - clicking
  "Create Invoice" still works exactly as before if that's fine for
  that order.

Confirmed still true in this version, since it's easy to lose track of
in a module that keeps growing: the "Create Invoice" button is only
ever visible to the dedicated custom group, Settings Administrators,
or native Accountant-level users - never to Salespeople or Sales
Administrators. See "The fix" section below for how that's enforced.

## What changed in v18.0.5.0.0

**New: Payment Proof.** Odoo's online payment integration isn't used in
this business - customers pay some other way (bank transfer, mobile
money, etc.), and until now that payment was only ever communicated to
Accounting verbally.

- A new **"Payment Proof"** field appears on the Sales Order form, right
  after "Payment Terms" - but only once the order is **confirmed**
  (draft/sent quotations don't show it, since there's nothing to attach
  proof of yet).
- The salesperson uploads a screenshot or scan (PDF, JPG, JPEG, or PNG)
  of the customer's payment confirmation directly onto the order.
- For the accountant (or anyone with "Can Create Invoice from Sales
  Order"), the field renders read-only - a plain view/download link,
  no upload button - matching how they already can't write to
  `sale.order` at all (see the existing `perm_write=0` access rule
  below). The readonly is just the UI treatment; that access rule is
  the real enforcement.
- The **"Sales Orders: To Invoice"** worklist (Accounting > Customers)
  now has a **"Payment Proof"** column, so Accounting can see at a
  glance which orders already have proof attached before opening them.

## What changed in v18.0.4.0.0

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
