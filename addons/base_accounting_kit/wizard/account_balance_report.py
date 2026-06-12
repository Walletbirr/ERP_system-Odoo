# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from odoo import api, fields, models, _


class AccountBalanceReport(models.TransientModel):
    _name = 'account.balance.report'
    _inherit = "account.common.account.report"
    _description = 'Trial Balance Report'

    section_report_ids = fields.Many2many(string="Sections",
                                          comodel_name='account.report',
                                          relation="account_balance_report_section_rel",
                                          column1="main_report_id",
                                          column2="sub_report_id")
    section_main_report_ids = fields.Many2many(string="Section Of",
                                               comodel_name='account.report',
                                               relation="account_balance_report_section_rel",
                                               column1="sub_report_id",
                                               column2="main_report_id")
    name = fields.Char(string="Trial Balance", default="Trial Balance", required=True, translate=True)
    journal_ids = fields.Many2many('account.journal',
                                   'account_balance_report_journal_rel',
                                   'account_id', 'journal_id',
                                   string='Journals', required=True,
                                   default=[])

    @api.model
    def _get_report_name(self):
        period_id = self._get_selected_period_id()
        return self.env['consolidation.period'].browse(period_id)['display_name'] or _("Trial Balance")

    def _print_report(self, data):
        data = self.pre_print_report(data)
        records = self.env[data['model']].browse(data.get('ids', []))
        return self.env.ref(
            'base_accounting_kit.action_report_trial_balance').report_action(
            records, data=data)
    def action_view_report(self):
        self.ensure_one()
        return self.view_report()

    def view_report(self):
        self.ensure_one()

        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')

        data['form'] = self.read([
            'date_from',
            'date_to',
            'journal_ids',
            'target_move',
            'company_id',
            'display_account',
        ])[0]

        used_context = self._build_contexts(data)
        data['form']['used_context'] = used_context

        records = self.env[data['model']].browse(data.get('ids', []))

        return self.env.ref(
            'base_accounting_kit.action_report_trial_balance_html'  # ⚠ needs confirming
        ).report_action(records, data=data)