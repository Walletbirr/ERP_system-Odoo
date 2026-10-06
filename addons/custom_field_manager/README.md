# Custom Management (Advanced) — Odoo 18

**Version:** 18.0.5.7.0

Control visibility, labels and behaviour of almost any UI element in Odoo 18
from one central place. Fully reversible, audited, no core module files touched.

## What you can manage

| Target | Actions | Typical examples |
|--------|---------|------------------|
| **Field** | Hide / Read-only / Required / Rename | Any field on any model (Form, List, Kanban) |
| **Notebook Tab** | Hide / Rename | "Settings", "Private Information" |
| **Button** | Hide / Rename | Header buttons, smart/stat buttons |
| **Menu Item** | Hide / Rename | **Any depth**: Apps, sub-menus, sub-sub-menus and deeper (full path + depth shown after selection) |
| **Window Action / Page Title** | Rename only | "Journal Entries", "Customer Payments", "Customers" |
| **Selection / Radio Option** | Hide / Rename | **Send** / **Receive** on Customer Payments, any other selection list |

## Quick start

1. Install the module (or upgrade from the previous 18.0.4.x version).
2. Go to **Custom Management → UI Element Rules**.
3. Create a rule, choose **Target Type**, fill the required fields, set **Action**, then click **Apply**.
4. Click **Revert** at any time to restore the original state.

### Renaming or hiding a Menu at any depth (Apps, sub, sub-sub, …)

1. Target Type = **Menu Item (Apps & sub-menus)**.
2. Search by the short name you see on screen (works for top-level Apps, sub-menus, **sub-sub-menus** and deeper).
3. After selecting, check **Full Menu Path**, **Parent Menu** and **Menu Depth** to confirm the correct level:
   - Depth 0 = top-level App  
   - Depth 1 = first submenu  
   - Depth 2+ = sub-sub-menu and deeper  
4. Action = **Rename** (fill New Label) or **Hide**.
5. Apply. Refresh the browser if needed. Hidden menus stay searchable so you can restore them later.

### Renaming a Page Title (e.g. "Journal Entries")

1. Target Type = **Window Action / Page Title**.
2. Search the current title and select the matching action.
3. Action = **Rename**, enter the new title.
4. Apply.

### Managing Send / Receive (or any Selection / Radio option)

1. Target Type = **Selection / Radio Option**.
2. Select the **Model** (e.g. `account.payment` / Customer Payment).
3. Select the **Selection Field** (e.g. Payment Type / `payment_type`).
4. Select the concrete **Option** (Send, Receive, …).
5. Action = **Rename** (new label) or **Hide**.
6. Apply.

- **Rename** changes the label everywhere the option is shown.
- **Hide** prefixes the label with `[hidden]` and moves it to the end of the list so it is practically invisible while remaining fully reversible.

### Controlling a Field / Tab / Button

Same workflow as before:

- Field → Model + Field + View Type + Action.
- Tab → Model + exact Tab Label (Form only).
- Button → Model + Button Label and/or Technical Name + View Type.

## Elements that appear more than once

Odoo screens often contain several copies of the same element (for example the
Journal Entry form has two **Other Info** tabs, one for invoices and one for plain
entries, and `journal_id` appears several times plus a separate label). A rule now
patches **every** copy and verifies the merged view. The **Last Apply Report** on the
rule shows how many elements were patched and verified. If a module installed later adds
another copy, click **Re-apply** on the rule (also available from the list's Action menu).

## Reverting & Auditing

- Open any applied rule → **Revert**. Everything returns to the original state.
- Deleting an applied rule automatically reverts it first.
- Every rule keeps a chatter log plus `Applied By` / `Applied On` fields.

## Important notes / Limitations

- **Server-required fields** cannot be hidden (blocked with a clear message). Use "Make Read-only".
- Tab and Button matching is by visible label (case-sensitive) unless you supply a Button Technical Name.
- Menu / Action / Selection changes write directly on the records (original values are stored on the rule so Revert works).
- After renaming a menu or page title a browser refresh (or re-opening the page) is usually enough.
- The module never touches core module source files → upgrades of Accounting, Sales, etc. stay safe.
- Window Action / Page Title supports **Rename only**: a page title cannot be hidden. To remove a screen, hide its Menu Item.
- Selection "Hide" is a soft-hide (label prefix + high sequence). True removal of a selection value would break existing records that still hold that value; soft-hide is the safe, reversible approach.

## Technical notes for developers

- Field / Tab / Button rules create high-priority (`priority=9999`) inherited views, one XPath per matched element, anchored on a unique `id`/`name` with positional fallback.
- Menu / Action / Selection Option rules store the original values on the rule record and write the new value on `ir.ui.menu` / `ir.actions.act_window` / `ir.model.fields.selection`.
- All operations are reversible and leave an audit trail via `mail.thread`.
- Security group: `custom_field_manager.group_field_manager` (implies System Administrator).

## Upgrade notes

**From 18.0.5.6.x or older:** upgrade normally. An `end-migration` script re-applies every applied
Field / Tab / Button rule with the new engine (older versions patched only the first match, so
tabs/fields could stay visible in other variants of the form). If a rule cannot be rebuilt it is left
untouched and a warning is logged; open it and click **Re-apply**.

**Changes in 18.0.5.7.0:** all matches are patched and verified; `<label for>` of hidden/renamed
fields is handled; Window Action Hide removed (it never worked) and its Revert fixed;
Re-apply button; configuration locked while a rule is applied.
