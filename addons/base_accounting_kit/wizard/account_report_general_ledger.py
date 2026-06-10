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
from odoo import fields, models, _
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountReportGeneralLedger(models.TransientModel):
    _name = "account.report.general.ledger"
    _inherit = "account.common.account.report"
    _description = "General Ledger Report"
    date_range_id = fields.Many2one(
        "date.range",
        string="Period"
    )

    @api.onchange("date_range_id")
    def _onchange_date_range_id(self):
        if self.date_range_id:
            self.date_from = self.date_range_id.date_start
            self.date_to = self.date_range_id.date_end

    account_ids = fields.Many2many(
    'account.account',
    string='Accounts'
    )
    show_journal = fields.Boolean(
    string="Show Journal",
    default=True
    )

    show_partner = fields.Boolean(
    string="Show Partner",
    default=True
    )

    show_ref = fields.Boolean(
        string="Show Reference",
        default=True
    )

    show_move = fields.Boolean(
        string="Show Move",
        default=True
    )

    show_entry_label = fields.Boolean(
        string="Show Entry Label",
        default=True
    )


    section_main_report_ids = fields.Many2many(string="Section Of",
                                               comodel_name='account.report',
                                               relation="account_report_general_section_rel",
                                               column1="sub_report_id",
                                               column2="main_report_id")
    section_report_ids = fields.Many2many(string="Sections",
                                          comodel_name='account.report',
                                          relation="account_report_general_section_rel",
                                          column1="main_report_id",
                                          column2="sub_report_id")
    name = fields.Char(string="General Ledger", default="General Ledger", required=True, translate=True)
    initial_balance = fields.Boolean(string='Include Initial Balances',
                                     help='If you selected date, this field '
                                          'allow you to add a row to display '
                                          'the amount of debit/credit/balance '
                                          'that precedes the filter you\'ve '
                                          'set.')
    sortby = fields.Selection(
        [('sort_date', 'Date'), ('sort_journal_partner', 'Journal & Partner')],
        string='Sort by', required=True, default='sort_date')
    journal_ids = fields.Many2many('account.journal',
                                   'account_report_general_ledger_journal_rel',
                                   'account_id', 'journal_id',
                                   string='Journals', required=True)

    def action_view_report(self):
        self.ensure_one()
        return self.view_report()

    def view_report(self):
        self.ensure_one()

        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get(
            'active_model',
            'ir.ui.menu'
        )

        data['form'] = self.read([
            'date_from',
            'date_to',
            'journal_ids',
            'target_move',
            'company_id',
            'display_account',
            'initial_balance',
            'sortby',
            'show_journal',
            'show_partner',
            'show_ref',
            'show_move',
            'show_entry_label',
            'account_ids',
        ])[0]

        used_context = self._build_contexts(data)
        data['form']['used_context'] = used_context

        records = self.env[data['model']].browse(
            data.get('ids', [])
        )

        return self.env.ref(
            'base_accounting_kit.action_report_general_ledger_html'
        ).report_action(
            records,
            data=data
        )
    #----- print report -----
    
    def _print_report(self, data):
        data = self.pre_print_report(data)
        # data['form'].update(self.read(['initial_balance', 'sortby'])[0])
        data['form'].update(
            self.read([
                'initial_balance',
                'sortby',
                'show_journal',
                'show_partner',
                'show_ref',
                'show_move',
                'show_entry_label',
                'account_ids',
            ])[0]
        )
        if data['form'].get('initial_balance') and not data['form'].get(
                'date_from'):
            raise UserError(_("You must define a Start Date"))
        records = self.env[data['model']].browse(data.get('ids', []))
        return self.env.ref(
            'base_accounting_kit.action_report_general_ledger').with_context(
            landscape=True).report_action(records, data=data)
