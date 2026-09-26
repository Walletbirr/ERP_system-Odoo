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
from odoo import fields, models


class AccountPrintJournal(models.TransientModel):
    _name = "account.print.journal"
    _inherit = "account.common.journal.report"
    _description = "Account Print Journal"

    section_main_report_ids = fields.Many2many(string="Section Of",
                                               comodel_name='account.report',
                                               relation="account_common_print_report_section_rel",
                                               column1="sub_report_id",
                                               column2="main_report_id")
    section_report_ids = fields.Many2many(string="Sections",
                                          comodel_name='account.report',
                                          relation="account_common_print_report_section_rel",
                                          column1="main_report_id",
                                          column2="sub_report_id")
    name = fields.Char(string="Journal Audit", default="Journal Audit", required=True, translate=True)
    sort_selection = fields.Selection(
        [('date', 'Date'), ('move_name', 'Journal Entry Number')],
        'Entries Sorted by', required=True, default='move_name')
    journal_ids = fields.Many2many('account.journal', string='Journals',
                                   required=True,
                                   default=lambda self: self.env[
                                       'account.journal'].search(
                                       [('type', 'in', ['sale', 'purchase'])]))

    def action_view_report(self):
        """View button - opens HTML report"""
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'date_to', 'journal_ids', 'target_move',
             'sort_selection', 'amount_currency', 'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = used_context
        data = self.pre_print_report(data)
        data['form'].update({'sort_selection': self.sort_selection, 'amount_currency': self.amount_currency})
        
        return self.env.ref(
            'base_accounting_kit.action_report_journal_html'
        ).report_action(self, data=data)

    def print_xlsx(self):
        """Excel export button"""
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'date_to', 'journal_ids', 'target_move',
             'sort_selection', 'amount_currency', 'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = used_context
        data = self.pre_print_report(data)
        data['form'].update({'sort_selection': self.sort_selection, 'amount_currency': self.amount_currency})
        
        return self.env.ref(
            'base_accounting_kit.action_report_journal_xlsx'
        ).report_action(self, data=data)

    def _print_report(self, data):
        data = self.pre_print_report(data)
        data['form'].update({'sort_selection': self.sort_selection})
        return self.env.ref(
            'base_accounting_kit.action_report_journal').with_context(
            landscape=True).report_action(self, data=data)


class JournalAuditXlsx(models.AbstractModel):
    """Excel export for Journal Audit"""
    _name = 'report.base_accounting_kit.report_journal_audit_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Journal Audit Excel'

    def generate_xlsx_report(self, workbook, data, objects):
        """Generate Excel report for Journal Audit"""
        sheet = workbook.add_worksheet('Journal Audit')
        sheet.set_landscape()
        
        # Formats
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9D9D9', 'border': 1})
        money_fmt = workbook.add_format({'num_format': '#,##0.00'})
        
        # Title
        sheet.write(0, 0, 'Journal Audit', title_fmt)
        row = 2
        
        # Headers
        sheet.write(row, 0, 'Date', header_fmt)
        sheet.write(row, 1, 'Journal', header_fmt)
        sheet.write(row, 2, 'Partner', header_fmt)
        sheet.write(row, 3, 'Account', header_fmt)
        sheet.write(row, 4, 'Entry Label', header_fmt)
        sheet.write(row, 5, 'Debit', header_fmt)
        sheet.write(row, 6, 'Credit', header_fmt)
        
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 4, 18)
        sheet.set_column(5, 6, 15)
        
        row += 1
        # Note: Actual data rendering would need the report data structure
        # This is a basic template - full implementation would iterate through journal entries
