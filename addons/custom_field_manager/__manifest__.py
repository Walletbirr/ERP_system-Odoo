# -*- coding: utf-8 -*-
{
    "name": "Custom Management (Advanced)",
    "version": "18.0.5.7.0",
    "category": "Customizations",
    "summary": "Hide, rename, make readonly/required any field, notebook tab, button, "
               "menu (Apps & sub-menus), window action / page title, or selection option "
               "(e.g. Send / Receive) — no core edits, fully reversible.",
    "description": """
Custom Management (Advanced)
============================
Control visibility, labels and behavior of almost any UI element in Odoo 18
from one central place. Fully reversible, audited, no core module files touched.

What you can manage
-------------------
* **Fields** — Hide / Read-only / Required / Rename (any model, Form / List / Kanban)
* **Notebook Tabs** — Hide or Rename entire tabs (e.g. "Settings", "Private Information")
* **Buttons** — Hide or Rename header buttons and smart/stat buttons
* **Menu Items** — Rename or Hide any menu including top-level Apps and deep sub-menus
  (Accounting → Accounting → Journal Entries, etc.)
* **Window Actions / Page Titles** — Rename the title shown at the top of list/form screens
  (e.g. change "Journal Entries" or "Customer Payments"). To remove a screen, hide its menu.
* **Selection Options** — Rename (or hide) individual values of a Selection / Radio field
  such as **Send** and **Receive** on Customer Payments, or any other selection list

Key properties
--------------
* Applies instantly via high-priority inherited views or direct reversible writes
* Patches EVERY copy of an element (e.g. both "Other Info" tabs of Journal Entries,
  a field repeated in the form plus its separate label) and verifies the result
* One-click Revert restores original state
* Full chatter audit trail (who applied/reverted and when)
* Safe for community & enterprise; survives module upgrades of Accounting, Sales, etc.
* Dedicated security group (Field Manager / Administrator)

Typical use-cases
-----------------
* Localise menu names and page titles to your language or company terminology
* Hide unused tabs, buttons or selection choices without Studio / code
* Make sensitive fields read-only for certain processes
* Clean the Apps switcher and sidebar by hiding or renaming items
    """,
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["base", "mail"],
    "data": [
        "security/field_manager_security.xml",
        "security/ir.model.access.csv",
        "views/field_manager_rule_views.xml",
        "views/field_manager_menu.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
