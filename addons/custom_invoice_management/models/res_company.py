# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    cim_service_charge_account_id = fields.Many2one(
        'account.account',
        string="Service Charge Income Account",
        domain="[('account_type', 'in', ('income', 'income_other')), "
               "('company_ids', 'in', id)]",
        help="Income account used for the Service Charge line(s) the "
             "\"Balance\" button generates on customer invoices. Leave "
             "empty to fall back to the Service Charge product's own "
             "Income Account (Accounting tab), or its Product Category's "
             "Income Account if that is empty too.",
    )

    @api.model
    def _cim_post_install_setup(self):
        """Runs on install (via post_init_hook) AND on every module
        upgrade (via a <function> record in data/post_install_data.xml -
        post_init_hook only fires on a fresh install, never on upgrade,
        so the <function> record is what makes this self-healing for
        people upgrading an already-installed copy of this module).

        Idempotent: safe to call repeatedly, never overwrites a manual
        choice, never creates a duplicate menu item.
        """
        self._cim_configure_service_charge_account_default()
        self._cim_add_menu_next_to_tax_groups()

    def _cim_configure_service_charge_account_default(self):
        """Give the 'Service Charge Income Account' setting a sensible
        out-of-the-box default, per company, so the Service Charge lines
        the 'Balance' button generates don't silently land on whatever
        account a completely unrelated product category happens to use.

        Only fills in companies that don't already have a value (so it
        never overwrites a choice made through Accounting > Configuration
        > Custom Invoice Management), and only if an 'Other Income' type
        account actually exists for that company - otherwise it leaves
        the setting empty and the module falls back to the Service
        Charge product's own Income Account / its Product Category's.
        """
        AccountAccount = self.env['account.account']
        for company in self.env['res.company'].search([]):
            if company.cim_service_charge_account_id:
                continue
            other_income_account = AccountAccount.search([
                ('company_ids', 'in', company.id),
                ('account_type', '=', 'income_other'),
            ], limit=1)
            if other_income_account:
                company.cim_service_charge_account_id = other_income_account

    def _cim_add_menu_next_to_tax_groups(self):
        """Place the 'Custom Invoice Management' settings menu item right
        next to "Tax Groups", under Accounting's Configuration menu.

        The exact "Configuration > Accounting" submenu ID is not the
        same across every Odoo 18 setup (custom accounting apps/kits can
        reorganise it), so instead of hardcoding a menu ID that could be
        wrong and break installation, this looks up the actual "Tax
        Groups" menu item at run time via its action
        (account.action_tax_group, a stable, official Odoo external ID)
        and places the new menu item as its sibling. If that action
        can't be found for any reason (e.g. a heavily customised
        chart-of-accounts module), the menu item is simply skipped - the
        setting is still fully reachable from Accounting > Configuration
        > Settings > Custom Invoice Management, so nothing is lost, only
        the shortcut.
        """
        env = self.env
        tax_group_action = env.ref('account.action_tax_group', raise_if_not_found=False)
        if not tax_group_action:
            return

        tax_group_menu = env['ir.ui.menu'].search([
            ('action', '=', 'ir.actions.act_window,%d' % tax_group_action.id),
        ], limit=1)
        if not tax_group_menu:
            return

        cim_action = env.ref(
            'custom_invoice_management.action_res_company_cim_settings',
            raise_if_not_found=False,
        )
        if not cim_action:
            return

        existing = env['ir.ui.menu'].search([
            ('action', '=', 'ir.actions.act_window,%d' % cim_action.id),
            ('parent_id', '=', tax_group_menu.parent_id.id),
        ], limit=1)
        if existing:
            return

        env['ir.ui.menu'].create({
            'name': 'Custom Invoice Management',
            'parent_id': tax_group_menu.parent_id.id,
            'action': 'ir.actions.act_window,%d' % cim_action.id,
            'sequence': tax_group_menu.sequence + 1,
        })
