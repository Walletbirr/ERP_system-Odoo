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
import re
from odoo import api, models, fields, _
from odoo.exceptions import UserError


class FinancialReport(models.TransientModel):
    _name = "financial.report"
    _inherit = "account.report"
    _description = "Financial Reports"

    section_main_report_ids = fields.Many2many(string="Section Of",
                                               comodel_name='account.report',
                                               relation="account_financial_report_section_rel",
                                               column1="sub_report_id",
                                               column2="main_report_id")
    section_report_ids = fields.Many2many(string="Sections",
                                          comodel_name='account.report',
                                          relation="account_financial_report_section_rel",
                                          column1="main_report_id",
                                          column2="sub_report_id")
    name = fields.Char(string="Financial Report", default="Financial Report", required=True, translate=True)

    target_move = fields.Selection([('posted', 'All Posted Entries'),
                                    ('all', 'All Entries'),
                                    ], string='Target Moves', required=True, default='posted')

    view_format = fields.Selection([
        ('vertical', 'Vertical'),
        ('horizontal', 'Horizontal')],
        default='vertical',
        string="Format")


    def _build_contexts(self, data):
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form'][
            'journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form'][
            'target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        return result

    @api.model
    def _get_account_report(self):
        reports = []
        if self._context.get('active_id'):
            menu = self.env['ir.ui.menu'].browse(
                self._context.get('active_id')).name
            reports = self.env['account.financial.report'].search([
                ('name', 'ilike', menu)])
        return reports and reports[0] or False

    enable_filter = fields.Boolean(
        string='Enable Comparison',
        default=False)
    account_report_id = fields.Many2one(
        'account.financial.report',
        string='Account Reports',
        required=True)

    date_from = fields.Date(string='Start Date')
    date_to = fields.Date(string='End Date')
    debit_credit = fields.Boolean(
        string='Display Debit/Credit Columns',
        default=True,
        help="This option allows you to"
             " get more details about the "
             "way your balances are computed."
             " Because it is space consuming,"
             " we do not allow to use it "
             "while doing a comparison.")
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        index=True,
        default=lambda self: self.env.company.id)

    def action_view_report(self):
        """View button - opens HTML report same as General Ledger"""
        self.ensure_one()
        
        data = dict()
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'enable_filter', 'debit_credit', 'date_to',
             'account_report_id', 'target_move', 'view_format',
             'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(
            used_context,
            lang=self.env.context.get('lang') or 'en_US')

        records = self.env[data['model']].browse(data.get('ids', []))
        
        return self.env.ref(
            'base_accounting_kit.financial_report_html'
        ).report_action(records, data=data)

    def print_xlsx(self):
        """Excel export button"""
        self.ensure_one()
        data = dict()
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'enable_filter', 'debit_credit', 'date_to',
             'account_report_id', 'target_move', 'view_format',
             'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(
            used_context,
            lang=self.env.context.get('lang') or 'en_US')

        # Process report data for Excel
        report_lines = self.get_account_lines(data['form'])
        journal_items = self.find_journal_items(report_lines, data['form'])

        def set_report_level(rec):
            level = 1
            if not rec['parent']:
                return level
            else:
                for line in report_lines:
                    key = 'a_id' if line['type'] == 'account' else 'id'
                    if line[key] == rec['parent']:
                        return level + set_report_level(line)

        for item in report_lines:
            item['balance'] = round(item['balance'], 2)
            if not item['parent']:
                item['level'] = 1
            else:
                item['level'] = set_report_level(item)

        currency = self._get_currency()
        data['currency'] = currency
        data['journal_items'] = journal_items
        data['report_lines'] = report_lines

        return self.env.ref(
            'base_accounting_kit.financial_report_xlsx'
        ).report_action(self, data=data)

    def view_report_pdf(self):
        """This function will be executed when we click the view button
        from the wizard. Based on the values provided in the wizard, this
        function will print pdf report"""
        self.ensure_one()
        data = dict()
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'enable_filter', 'debit_credit', 'date_to',
             'account_report_id', 'target_move', 'view_format',
             'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(
            used_context,
            lang=self.env.context.get('lang') or 'en_US')

        report_lines = self.get_account_lines(data['form'])
        # find the journal items of these accounts
        journal_items = self.find_journal_items(report_lines, data['form'])

        def set_report_level(rec):
            """This function is used to set the level of each item.
            This level will be used to set the alignment in the dynamic reports."""
            level = 1
            if not rec['parent']:
                return level
            else:
                for line in report_lines:
                    key = 'a_id' if line['type'] == 'account' else 'id'
                    if line[key] == rec['parent']:
                        return level + set_report_level(line)

        # finding the root
        for item in report_lines:
            item['balance'] = round(item['balance'], 2)
            if not item['parent']:
                item['level'] = 1
                parent = item
                report_name = item['name']
                id = item['id']
                report_id = item['r_id']
            else:
                item['level'] = set_report_level(item)
        currency = self._get_currency()
        data['currency'] = currency
        data['journal_items'] = journal_items
        data['report_lines'] = report_lines
        # checking view type
        return self.env.ref(
            'base_accounting_kit.financial_report_pdf').report_action(self,
                                                                      data)

    def _compute_account_balance(self, accounts):
        """ compute the balance, debit
        and credit for the provided accounts
        """
        mapping = {
            'balance':
                "COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0)"
                " as balance",
            'debit': "COALESCE(SUM(debit), 0) as debit",
            'credit': "COALESCE(SUM(credit), 0) as credit",
        }

        res = {}
        for account in accounts:
            res[account.id] = dict((fn, 0.0)
                                   for fn in mapping.keys())
        if accounts:
            tables, where_clause, where_params = (
                self.env['account.move.line']._query_get())
            tables = tables.replace(
                '"', '') if tables else "account_move_line"
            wheres = [""]
            if where_clause.strip():
                wheres.append(where_clause.strip())
            filters = " AND ".join(wheres)
            request = ("SELECT account_id as id, " +
                       ', '.join(mapping.values()) +
                       " FROM " + tables +
                       " WHERE account_id IN %s " +
                       filters +
                       " GROUP BY account_id")
            params = (tuple(accounts._ids),) + tuple(where_params)
            self.env.cr.execute(request, params)
            for row in self.env.cr.dictfetchall():
                res[row['id']] = row
        return res

    def _compute_report_balance(self, reports):
        """returns a dictionary with key=the ID of a record and
         value=the credit, debit and balance amount
        computed for this record. If the record is of type :
        'accounts' : it's the sum of the linked accounts
        'account_type' : it's the sum of leaf accounts with
         such an account_type
        'account_report' : it's the amount of the related report
        'sum' : it's the sum of the children of this record
         (aka a 'view' record)"""
        res = {}
        fields = ['credit', 'debit', 'balance']
        for report in reports:
            if report.id in res:
                continue
            res[report.id] = dict((fn, 0.0) for fn in fields)
            if report.type == 'accounts':
                # it's the sum of the linked accounts
                res[report.id]['account'] = self._compute_account_balance(
                    report.account_ids
                )
                for value in \
                        res[report.id]['account'].values():
                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == 'account_type':
                # it's the sum the leaf accounts
                #  with such an account type
                accounts = self.env['account.account'].search([
                    ('account_type', '=', report.account_type_ids)
                ])
                if report.name == "Expenses":
                    accounts = self.env['account.account'].search([
                        ('account_type', 'in', ["expense","expense_depreciation","expense_direct_cost"])
                    ])
                if report.name == "Liability":
                    accounts = self.env['account.account'].search([
                        ('account_type', 'in', ["liability_payable","equity","liability_current","liability_non_current"])
                    ])
                if report.name == "Assets":
                    accounts = self.env['account.account'].search([
                        ('account_type', 'in', ["asset_receivable","asset_cash","asset_current","asset_non_current","asset_prepayments","asset_fixed"])
                    ])

                res[report.id]['account'] = self._compute_account_balance(
                    accounts)

                for value in res[report.id]['account'].values():
                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == 'account_report' and report.account_report_id:
                # it's the amount of the linked report
                res2 = self._compute_report_balance(report.account_report_id)
                for key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
            elif report.type == 'sum':
                # it's the sum of the children of this account.report
                res2 = self._compute_report_balance(report.children_ids)
                for key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
        return res

    def get_account_lines(self, data):
        lines = []
        account_report = self.env['account.financial.report'].search([
            ('id', '=', data['account_report_id'][0])
        ])
        child_reports = account_report._get_children_by_order()
        res = self.with_context(
            data.get('used_context'))._compute_report_balance(child_reports)
        if data['enable_filter']:
            comparison_res = self._compute_report_balance(child_reports)
            for report_id, value in comparison_res.items():
                res[report_id]['comp_bal'] = value['balance']
                report_acc = res[report_id].get('account')
                if report_acc:
                    for account_id, val in \
                            comparison_res[report_id].get('account').items():
                        report_acc[account_id]['comp_bal'] = val['balance']

        for report in child_reports:
            r_name = str(report.name)
            r_name = re.sub('[^0-9a-zA-Z]+', '', r_name)
            if report.parent_id:
                p_name = str(report.parent_id.name)
                p_name = re.sub('[^0-9a-zA-Z]+', '', p_name) + str(
                    report.parent_id.id)
            else:
                p_name = False
            vals = {
                'r_id': report.id,
                'id': r_name + str(report.id),
                'sequence': report.sequence,
                'parent': p_name,
                'name': report.name,
                'balance': res[report.id]['balance'] * int(report.sign),
                'type': 'report',
                'level': bool(
                    report.style_overwrite) and report.style_overwrite or
                         report.level,
                'account_type': report.type or False,
                # used to underline the financial report balances
            }
            if data['debit_credit']:
                vals['debit'] = res[report.id]['debit']
                vals['credit'] = res[report.id]['credit']

            if data['enable_filter']:
                vals['balance_cmp'] = res[report.id]['comp_bal'] * int(
                    report.sign)

            lines.append(vals)
            if report.display_detail == 'no_detail':
                # the rest of the loop is
                # used to display the details of the
                #  financial report, so it's not needed here.
                continue

            if res[report.id].get('account'):
                sub_lines = []
                for account_id, value \
                        in res[report.id]['account'].items():
                    # if there are accounts to display,
                    #  we add them to the lines with a level equals
                    #  to their level in
                    # the COA + 1 (to avoid having them with a too low level
                    #  that would conflicts with the level of data
                    # financial reports for Assets, liabilities...)
                    flag = False
                    account = self.env['account.account'].browse(account_id)
                    # new_r_name = str(report.name)
                    # new_r_name = new_r_name.replace(" ", "-") + "-"
                    vals = {
                        'account': account.id,
                        'a_id': account.code + re.sub('[^0-9a-zA-Z]+', 'acnt',
                                                      account.name) + str(
                            account.id),
                        'name': account.code + '-' + account.name,
                        'balance': value['balance'] * int(report.sign) or 0.0,
                        'type': 'account',
                        'parent': r_name + str(report.id),
                        'level': (
                                report.display_detail == 'detail_with_hierarchy' and
                                4),
                        'account_type': account.account_type,
                    }
                    if data['debit_credit']:
                        vals['debit'] = value['debit']
                        vals['credit'] = value['credit']
                        for company in account.company_ids:
                            if not company.currency_id.is_zero(
                                    vals['debit']) or \
                                    not company.currency_id.is_zero(
                                        vals['credit']):
                                flag = True
                    for company in account.company_ids:
                        if not company.currency_id.is_zero(
                                vals['balance']):
                            flag = True
                    if data['enable_filter']:
                        vals['balance_cmp'] = value['comp_bal'] * int(
                            report.sign)
                        for company in account.company_ids:
                            if not company.currency_id.is_zero(
                                    vals['balance_cmp']):
                                flag = True
                    if flag:
                        sub_lines.append(vals)
                lines += sorted(sub_lines,
                                key=lambda sub_line: sub_line['name'])
        return lines

    def find_journal_items(self, report_lines, form):
        cr = self.env.cr
        journal_items = []
        for i in report_lines:
            if i['type'] == 'account':
                account = i['account']
                if form['target_move'] == 'posted':
                    search_query = ("select aml.id, am.id as j_id, "
                                    "aml.account_id, aml.date, aml.name as "
                                    "label, am.name, (aml.debit-aml.credit) as "
                                    "balance, aml.debit, aml.credit, "
                                    "aml.partner_id  from "
                                    "account_move_line aml "
                                    "join account_move am on (aml.move_id=am.id"
                                    " and am.state=%s) where aml.account_id=%s")
                    vals = [form['target_move']]
                else:
                    search_query = ("select aml.id, am.id as j_id, "
                                    "aml.account_id, aml.date, aml.name as "
                                    "label, am.name, (aml.debit-aml.credit) as "
                                    "balance, aml.debit, aml.credit, "
                                    "aml.partner_id from account_move_line aml"
                                    " join account_move am on "
                                    "(aml.move_id=am.id) where "
                                    "aml.account_id=%s")
                    vals = []
                if form['date_from'] and form['date_to']:
                    search_query += " and aml.date>=%s and aml.date<=%s"
                    vals += [account, form['date_from'], form['date_to']]
                elif form['date_from']:
                    search_query += " and aml.date>=%s"
                    vals += [account, form['date_from']]
                elif form['date_to']:
                    search_query += " and aml.date<=%s"
                    vals += [account, form['date_to']]
                else:
                    vals += [account]
                cr.execute(search_query, tuple(vals))
                items = cr.dictfetchall()

                for j in items:
                    temp = j['id']
                    j['id'] = re.sub('[^0-9a-zA-Z]+', '', i['name']) + str(
                        temp)
                    j['p_id'] = str(i['a_id'])
                    j['type'] = 'journal_item'
                    journal_items.append(j)
        return journal_items

    @api.model
    def _get_currency(self):
        journal = self.env['account.journal'].browse(
            self.env.context.get('default_journal_id', False))
        if journal.currency_id:
            return journal.currency_id.id
        return self.env.company.currency_id.symbol


class ProfitLossPdf(models.AbstractModel):
    """ Abstract model for generating PDF report value and send to template """

    _name = 'report.base_accounting_kit.report_financial'
    _description = 'Financial Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        """ Provide report values to template - compute report lines here like GL does """
        if not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        
        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_ids', []))
        
        # Get wizard record to access methods
        wizard = self.env['financial.report'].browse(docids)
        
        # Compute report lines and journal items
        report_lines = wizard.get_account_lines(data['form'])
        journal_items = wizard.find_journal_items(report_lines, data['form'])

        def set_report_level(rec):
            level = 1
            if not rec['parent']:
                return level
            else:
                for line in report_lines:
                    key = 'a_id' if line['type'] == 'account' else 'id'
                    if line[key] == rec['parent']:
                        return level + set_report_level(line)

        for item in report_lines:
            item['balance'] = round(item['balance'], 2)
            if not item['parent']:
                item['level'] = 1
            else:
                item['level'] = set_report_level(item)

        currency = wizard._get_currency()
        
        return {
            'doc_ids': docids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'report_lines': report_lines,
            'journal_items': journal_items,
            'account_report': data['form']['account_report_id'][1],
            'currency': currency,
        }


class FinancialReportXlsx(models.AbstractModel):
    """Excel export for Financial Reports"""
    _name = 'report.base_accounting_kit.report_financial_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Financial Report Excel'

    def generate_xlsx_report(self, workbook, data, objects):
        """Generate Excel report with same data as PDF/HTML"""
        
        # Get form data
        form = data.get('form', {})
        
        # Get report lines and journal items (already computed and passed in data)
        report_lines = data.get('report_lines', [])
        currency_symbol = data.get('currency', '$')
        
        # Create worksheet
        sheet = workbook.add_worksheet('Financial Report')
        sheet.set_landscape()
        
        # Formats
        title_fmt = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center',
        })
        header_fmt = workbook.add_format({
            'bold': True,
            'bg_color': '#D9D9D9',
            'border': 1,
            'align': 'center',
        })
        bold_fmt = workbook.add_format({'bold': True})
        money_fmt = workbook.add_format({'num_format': '#,##0.00'})
        money_bold_fmt = workbook.add_format({
            'num_format': '#,##0.00',
            'bold': True,
        })
        
        # Title
        sheet.merge_range(0, 0, 0, 3, form.get('account_report_id', ['', 'Financial Report'])[1], title_fmt)
        sheet.set_column(0, 0, 50)  # Name column width
        sheet.set_column(1, 3, 15)  # Number columns width
        
        row = 2
        
        # Headers
        col = 0
        sheet.write(row, col, 'Name', header_fmt)
        col += 1
        
        if form.get('debit_credit'):
            sheet.write(row, col, 'Debit', header_fmt)
            col += 1
            sheet.write(row, col, 'Credit', header_fmt)
            col += 1
        
        sheet.write(row, col, 'Balance', header_fmt)
        row += 1
        
        # Report lines
        for line in report_lines:
            if line.get('level', 0) == 0:
                continue
                
            col = 0
            level = line.get('level', 1)
            indent = '  ' * (level - 1)
            name = indent + line.get('name', '')
            
            # Determine if bold (parent lines)
            is_bold = level <= 3
            name_fmt = bold_fmt if is_bold else None
            balance_fmt = money_bold_fmt if is_bold else money_fmt
            
            sheet.write(row, col, name, name_fmt)
            col += 1
            
            if form.get('debit_credit'):
                debit = line.get('debit', 0.0)
                credit = line.get('credit', 0.0)
                sheet.write(row, col, debit, balance_fmt)
                col += 1
                sheet.write(row, col, credit, balance_fmt)
                col += 1
            
            balance = line.get('balance', 0.0)
            sheet.write(row, col, balance, balance_fmt)
            row += 1
