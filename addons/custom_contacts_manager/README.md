# Custom Contacts Manager (Odoo 18)

Replaces the flat, everything-in-one-list Contacts view with categorized,
access-controlled contact management.

## What it does
- Adds a `Contact Category` model (`res.partner.classification`) — Internal
  User, Client, Customer, Vendor, Company by default. Add more from
  Contacts > Configuration > Contact Categories.
- Partners linked to a system user (`res.users`) are automatically forced
  into the "Internal User" category on create/write — this can't be
  overridden manually, so it can't be spoofed to dodge the security rules.
- Real record-rule security (not just UI filtering): a user without the
  "Can View Clients" group literally cannot query client records, including
  via API, reports, or exports — not just hidden from the menu.
- Separate top-level menu items: All Contacts (admin), Clients, Customers,
  Vendors, Companies, Internal Directory — each a scoped view of the same
  `res.partner` model.
- New kanban card design: category badge, color-coded avatar, condensed
  contact info.
- New list view grouped by category by default.

## Install
1. Copy the `custom_contacts_manager` folder into your Odoo `addons` path.
2. Restart the Odoo service.
3. Activate developer mode > Apps > Update Apps List.
4. Search "Custom Contacts Manager" and install.

## After install — required steps
1. **Backfill existing contacts.** New/edited contacts get auto-classified,
   but your existing 35 contacts (as of this build) won't have a category
   yet. Go to Contacts > All Contacts, select all, and bulk-set
   "Contact Category" — or run a one-time script:
   ```python
   # via Odoo shell: odoo-bin shell -d your_db
   env['res.partner']._auto_assign_internal_classification()
   # then manually set contact_type_id for the rest by company/individual
   ```
2. **Assign security groups.** Go to Settings > Users & Companies > Users,
   open each employee, and under the "Contacts Visibility" category tick
   the categories they should see (Can View Clients, Can View Vendors,
   etc.). Everyone in `base.group_user` sees Customers by default only.
   Admins (`base.group_system`) get full access automatically.
3. **Review the search-view patch.** `views/res_partner_views.xml` patches
   `base.view_res_partner_filter` by inserting after the `category_id`
   field. If your Odoo 18 build has a customized base Contacts search view,
   double check this xpath still matches after installing other Contacts
   customizations.

## Extending
- Add more categories any time from Configuration > Contact Categories —
  no code change needed, menus/kanban pick up the color and icon
  automatically.
- To scope visibility further (e.g. sales reps see only their own
  clients), edit `security/security.xml` and add `('user_id', '=',
  user.id)` to the relevant rule's domain.
- To make certain form fields appear only for specific categories, add
  `invisible="contact_type_code != 'client'"` (Odoo 18 syntax) to the
  relevant `<field>`/`<group>` in a new inherited form view.
