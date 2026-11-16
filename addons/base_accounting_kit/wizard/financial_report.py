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
from odoo import api, models, fields


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

    def _build_report_data(self):
        """Shared helper: build the data dict and resolved report_lines used
        by both the PDF and Excel export paths."""
        self.ensure_one()
        data = {}
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
        journal_items = self.find_journal_items(report_lines, data['form'])

        def set_report_level(rec):
            level = 1
            if not rec['parent']:
                return level
            for line in report_lines:
                key = 'a_id' if line['type'] == 'account' else 'id'
                if line[key] == rec['parent']:
                    return level + set_report_level(line)
            return level

        for item in report_lines:
            item['balance'] = round(item['balance'], 2)
            if not item['parent']:
                item['level'] = 1
            else:
                item['level'] = set_report_level(item)

        data['currency'] = self._get_currency()
        data['journal_items'] = journal_items
        data['report_lines'] = report_lines
        return data

    def view_report_pdf(self):
        """Print the financial report as PDF."""
        data = self._build_report_data()
        return self.env.ref(
            'base_accounting_kit.financial_report_pdf').report_action(self,
                                                                      data)

    def print_xlsx(self):
        """Export the financial report as Excel."""
        data = self._build_report_data()
        return self.env.ref(
            'base_accounting_kit.financial_report_xlsx').report_action(self,
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

    # Account types whose natural (normal) side is Credit.
    # For these, a positive balance means credit > debit, so we negate the
    # raw (debit - credit) value to show a positive number for normal balances.
    CREDIT_NORMAL_TYPES = {
        'income', 'income_other',
        'liability_payable', 'liability_credit_card',
        'liability_current', 'liability_non_current',
        'equity', 'equity_unaffected',
    }

    def _account_normal_side_sign(self, account_type):
        """Return -1 for credit-normal account types, +1 for debit-normal.

        This converts the raw (debit - credit) balance stored in the database
        into a 'normal side' amount where a positive value means the account
        has a balance on its natural side:
          - Debit-normal (assets, expenses, cost of revenue): positive = debit > credit
          - Credit-normal (income, liabilities, equity): positive = credit > debit
        """
        if account_type in self.CREDIT_NORMAL_TYPES:
            return -1
        return 1

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
                'type': 'report',
                'level': bool(
                    report.style_overwrite) and report.style_overwrite or
                         report.level,
                'account_type': report.type or False,
            }
            # Determine display sign for this group row:
            # - account_type nodes: use the natural side of the account type
            #   (income/liability = credit-normal → -1, expense/asset = +1)
            # - sum/account_report nodes: use report.sign from the database.
            #   Additionally, for any sum node whose database sign is still the
            #   default '1' but whose dominant child contribution comes from
            #   credit-normal account types, we override to -1 so the total
            #   shows positive when it should (handles Gross Profit on existing
            #   databases that were installed before the XML sign correction).
            if report.type == 'account_type':
                group_sign = self._account_normal_side_sign(
                    report.account_type_ids)
            elif report.type == 'sum' and int(report.sign) == 1:
                # Walk the direct account_type children and sum up what their
                # correctly-signed balances would be. If the net is negative
                # it means credit-normal children dominate, so flip to -1.
                children = report.children_ids
                signed_sum = 0.0
                for child in children:
                    child_raw = res.get(child.id, {}).get('balance', 0.0)
                    if child.type == 'account_type':
                        child_sign = self._account_normal_side_sign(
                            child.account_type_ids)
                    else:
                        child_sign = int(child.sign)
                    signed_sum += child_raw * child_sign
                # If the signed sum of children is positive but the raw total
                # is negative, we need sign=-1 to display correctly.
                raw_total = res[report.id]['balance']
                if raw_total != 0 and signed_sum != 0:
                    group_sign = -1 if (signed_sum > 0 and raw_total < 0) else 1
                else:
                    group_sign = 1
            else:
                group_sign = int(report.sign)
            vals['balance'] = res[report.id]['balance'] * group_sign
            if data['debit_credit']:
                vals['debit'] = res[report.id]['debit']
                vals['credit'] = res[report.id]['credit']

            if data['enable_filter']:
                vals['balance_cmp'] = res[report.id]['comp_bal'] * group_sign

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
                    # Determine the display sign based on the account's own
                    # normal side (debit-normal = +1, credit-normal = -1).
                    # This makes income/liability accounts show positive when
                    # they have a credit balance, and expense/asset accounts
                    # show positive when they have a debit balance.
                    acct_sign = self._account_normal_side_sign(
                        account.account_type)
                    vals = {
                        'account': account.id,
                        'a_id': account.code + re.sub('[^0-9a-zA-Z]+', 'acnt',
                                                      account.name) + str(
                            account.id),
                        'name': account.code + '-' + account.name,
                        'balance': value['balance'] * acct_sign or 0.0,
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
                        vals['balance_cmp'] = value['comp_bal'] * acct_sign
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
        """ Provide report values to template """
        ctx = {
            'data': data,
            'journal_items': data['journal_items'],
            'report_lines': data['report_lines'],
            'account_report': data['form']['account_report_id'][1],
            'currency': data['currency'],
        }
        return ctx


class FinancialReportXlsx(models.AbstractModel):
    """Excel export for financial reports (Profit & Loss, Balance Sheet).

    Layout mirrors the accountant's format:
      - Company + report name + period header
      - Section group rows: bold, no indent
      - Individual account rows: normal weight, indented
      - Subtotal rows (level <= 3, type='report', has parent): bold, top border
      - Root total row (no parent): bold, double top border
      - Negative net values shown as (amount) in accounting style
    """

    _name = 'report.base_accounting_kit.report_financial_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Financial Report Excel'

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _fmt_balance(self, value, currency_symbol):
        """Return an accounting-style string: negative shown as (1,234.56)."""
        if value < 0:
            return '({} {:,.2f})'.format(currency_symbol, abs(value))
        return '{} {:,.2f}'.format(currency_symbol, value)

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def generate_xlsx_report(self, workbook, data, objects):
        form = data.get('form', {})
        report_lines = data.get('report_lines', [])
        currency_symbol = self.env.company.currency_id.symbol
        report_name = form.get('account_report_id', [False, 'Financial Report'])[1]
        company_name = self.env.company.name
        date_from = form.get('date_from') or ''
        date_to = form.get('date_to') or ''
        show_debit_credit = form.get('debit_credit', False)

        # ---- worksheet ------------------------------------------------ #
        sheet = workbook.add_worksheet(report_name[:31])
        sheet.set_landscape()
        sheet.set_paper(9)           # A4
        sheet.fit_to_pages(1, 0)
        sheet.set_column(0, 0, 48)   # Name column
        if show_debit_credit:
            sheet.set_column(1, 1, 18)   # Debit
            sheet.set_column(2, 2, 18)   # Credit
            sheet.set_column(3, 3, 18)   # Balance
            balance_col = 3
        else:
            sheet.set_column(1, 1, 22)   # Balance
            balance_col = 1

        # ---- formats -------------------------------------------------- #
        def _fmt(**kwargs):
            return workbook.add_format(kwargs)

        title_fmt = _fmt(bold=True, font_size=14, align='center')
        subtitle_fmt = _fmt(bold=True, font_size=11, align='center')
        period_fmt = _fmt(italic=True, font_size=10, align='center')

        header_fmt = _fmt(bold=True, bg_color='#D9D9D9', border=1,
                          align='center', valign='vcenter')
        header_right_fmt = _fmt(bold=True, bg_color='#D9D9D9', border=1,
                                align='right', valign='vcenter')

        # section heading row (level 1-2 group, no parent or top-level)
        section_fmt = _fmt(bold=True, font_size=11)
        section_num_fmt = _fmt(bold=True, font_size=11,
                               num_format='#,##0.00', align='right')

        # individual account row
        account_fmt = _fmt(indent=1)
        account_num_fmt = _fmt(num_format='#,##0.00', align='right')

        # subtotal row (child group summary)
        subtotal_fmt = _fmt(bold=True, top=1)
        subtotal_num_fmt = _fmt(bold=True, top=1,
                                num_format='#,##0.00', align='right')

        # root total row (Profit and Loss / Balance Sheet total)
        total_fmt = _fmt(bold=True, top=6, font_size=11)   # top=6 → double line
        total_num_fmt = _fmt(bold=True, top=6, font_size=11,
                             num_format='#,##0.00', align='right')

        blank_fmt = _fmt()

        # ---- header rows ---------------------------------------------- #
        row = 0
        last_col = balance_col
        sheet.merge_range(row, 0, row, last_col, company_name, title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, last_col, report_name, subtitle_fmt)
        row += 1
        if date_from and date_to:
            period_str = 'From {} to {}'.format(date_from, date_to)
        elif date_to:
            period_str = 'As of {}'.format(date_to)
        elif date_from:
            period_str = 'From {}'.format(date_from)
        else:
            period_str = ''
        if period_str:
            sheet.merge_range(row, 0, row, last_col, period_str, period_fmt)
            row += 1
        row += 1  # blank spacer

        # ---- column headers ------------------------------------------- #
        sheet.write(row, 0, 'Name', header_fmt)
        if show_debit_credit:
            sheet.write(row, 1, 'Debit', header_right_fmt)
            sheet.write(row, 2, 'Credit', header_right_fmt)
            sheet.write(row, 3, 'Balance', header_right_fmt)
        else:
            sheet.write(row, 1, 'Balance', header_right_fmt)
        row += 1

        # ---- data rows ------------------------------------------------ #
        for line in report_lines:
            level = line.get('level', 1)
            line_type = line.get('type', 'report')   # 'report' or 'account'
            has_parent = bool(line.get('parent'))
            balance = line.get('balance', 0.0)
            name = line.get('name', '')

            # pick formats based on row role
            if line_type == 'account':
                # leaf account line
                name_fmt = account_fmt
                num_fmt = account_num_fmt
            elif not has_parent:
                # root total line (Profit and Loss / Balance Sheet)
                name_fmt = total_fmt
                num_fmt = total_num_fmt
            elif level <= 2:
                # top-level section heading (Income, Expense, etc.)
                name_fmt = section_fmt
                num_fmt = section_num_fmt
            else:
                # intermediate subtotal (Gross Profit, Operating Income, etc.)
                name_fmt = subtotal_fmt
                num_fmt = subtotal_num_fmt

            # indent account names visually with spaces
            display_name = ('    ' * max(0, level - 1)) + name if line_type == 'account' else name

            sheet.write(row, 0, display_name, name_fmt)

            if show_debit_credit:
                debit = line.get('debit', 0.0)
                credit = line.get('credit', 0.0)
                sheet.write(row, 1, debit if line_type == 'account' else (debit or ''), num_fmt)
                sheet.write(row, 2, credit if line_type == 'account' else (credit or ''), num_fmt)
                sheet.write(row, 3, balance, num_fmt)
            else:
                sheet.write(row, 1, balance, num_fmt)

            row += 1

            # blank spacer after every section heading (level <= 2, is a report row)
            if line_type == 'report' and level <= 2 and has_parent:
                # a small visual gap before the section's accounts start
                pass  # no extra blank — accounts follow immediately

        # ---- final blank + currency note ------------------------------ #
        row += 1
        note_fmt = _fmt(italic=True, font_color='#666666', font_size=9)
        sheet.merge_range(row, 0, row, last_col,
                          'All amounts in {}'.format(currency_symbol),
                          note_fmt)
