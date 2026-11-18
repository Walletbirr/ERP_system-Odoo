from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    # =========================================================
    # CONFIGURABLE DEFAULTS FOR LC MANAGEMENT
    # =========================================================
    # Fee account is intentionally NOT configured here - it's picked per LC
    # from the reference the user sets on the record itself, so there's
    # nothing to default company-wide.
    #
    # This replaces the old behaviour where the Opening/Settlement VAT
    # account was found by hard-coding a search for the literal account
    # name "VAT REC/PAY". If the Chart of Accounts ever renamed that
    # account, the field would simply come up empty with no way to fix it
    # short of a code change. Now it's a normal configuration field: set it
    # once per company, and every new LC/settlement line pre-fills from it
    # while still allowing the accountant to override it per record.
    lc_default_vat_account_id = fields.Many2one(
        'account.account',
        string="Default LC VAT Account",
        help="Automatically suggested as the Opening/Settlement VAT account "
             "on new Letters of Credit. Can still be changed per LC."
    )
    lc_default_accountant_id = fields.Many2one(
        'res.users',
        string="Default LC Accountant",
        help="Suggested by default as who to send new-account requests and "
             "payment approvals to. Can be overridden per request."
    )
    lc_default_margin_account_id = fields.Many2one(
        'account.account',
        string="Default Margin Account",
        help="Automatically suggested as the Margin Account on new Letters "
             "of Credit. Can still be changed per LC."
    )

    def action_open_lc_settings(self):
        """Opens a small, self-contained settings form scoped to just the
        LC Management fields on this company record. Deliberately does NOT
        hook into Settings > General Settings (res.config.settings) - this
        stays entirely inside the LC Management module's own menu."""
        company = self.env.company
        return {
            'type': 'ir.actions.act_window',
            'name': 'LC Management Settings',
            'res_model': 'res.company',
            'res_id': company.id,
            'view_mode': 'form',
            'view_id': self.env.ref('lc_management.view_lc_company_settings_form').id,
            'target': 'current',
            # Pin this to the LC Management > Configuration menu explicitly,
            # so the app stays "LC Management" in the sidebar no matter
            # where this action gets triggered from, instead of falling
            # back to whatever app res.company records are normally
            # associated with (Settings).
            'menu_id': self.env.ref('lc_management.menu_lc_config_settings').id,
        }
