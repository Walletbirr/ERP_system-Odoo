# Accounting - Create Vendor Bill from Purchase Order

Mirrors `accounting_so_invoice_bridge` exactly, for the Purchase -> Vendor
Bill side. Same architecture as your already-working Sales module:
- No wizard, no modal.
- A filtered full-page list of confirmed POs still needing a bill, under
  **Accounting/Invoicing > Vendors > Create Bill from Purchase Order**.
- Clicking a row opens the real, standard Purchase Order form.
- The native "Create Bill" button on that form is restricted to a
  dedicated custom permission, decoupled from the native Invoicing field.

## Installation

1. Copy the `purchase_bill_bridge` folder into your custom addons path.
2. Settings > General Settings > Developer Tools > Update Apps List.
3. Apps > search "Create Vendor Bill from Purchase Order" > Install.

## Setup after install (per real accountant)

Settings > Users & Companies > Users > pick the accountant > **Access
Rights** tab. Under the new category **"Purchase Order Billing (Custom)"**,
tick **"Can Create Bill from Purchase Order."** This is the ONLY thing that
turns the native button on for them - their native Invoicing field can be
left as-is or blank, it no longer matters.

## Manual access-rights steps (per user, Settings > Users & Companies > Users)

### Purchase Officers
| App        | Access level        |
|------------|----------------------|
| Purchase   | Purchase User (or Administrator, per your org) |
| Invoicing/Accounting | (blank / no access) |
| Custom "Purchase Order Billing" group | not ticked |

### Accountants / Finance (Accounts Payable)
| App        | Access level        |
|------------|----------------------|
| Purchase   | (blank / no access) - this module supplies the read-only bridge |
| Invoicing/Accounting | Billing, or Accountant for reconciliation/reports |
| Custom "Purchase Order Billing" group | ticked |

## Notes / verify on your instance before go-live

- The button selector targets `name="action_create_invoice"` (the
  method Odoo kept that name for, even though it produces a Vendor Bill).
  If `base_accounting_kit` has customized the Purchase Order form, test
  with a non-privileged user after install: if the button doesn't
  disappear for them, the selector needs adjusting to match your build's
  actual view - open Settings > Technical > Views and inspect
  `purchase.purchase_order_form` to confirm.
- Test with a Purchase-only test user (no custom group ticked): confirm
  the "Create Bill" button is gone/inactive for them.
- Test with an Accountant-only test user (no Purchase group at all, custom
  group ticked): confirm they can reach the new Vendors menu, open a
  confirmed PO in read-only, and successfully create the bill.
- This module only covers bill creation. Vendor payment registration is
  already correctly gated by the standard Billing/Accountant groups - no
  extra work needed there as long as Purchase Officers have no Invoicing
  access.
