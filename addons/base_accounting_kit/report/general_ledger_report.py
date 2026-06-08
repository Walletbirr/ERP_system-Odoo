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
import time
from odoo import api, models, _
from odoo.exceptions import UserError


class ReportGeneralLedger(models.AbstractModel):
    _name = 'report.base_accounting_kit.report_general_ledger'
    _description = 'General Ledger Report'

    def _get_account_move_entry(
        self,
        accounts,
        init_balance,
        sortby,
        display_account):

        cr = self.env.cr
        MoveLine = self.env['account.move.line']

        account_res = []

        # ---------------------------------------------------------
        # SORTING
        # ---------------------------------------------------------

        sql_sort = 'l.date, l.move_id'

        if sortby == 'sort_journal_partner':
            sql_sort = 'j.code, p.name, l.move_id'

        # ---------------------------------------------------------
        # MAIN QUERY
        # ---------------------------------------------------------

        tables, where_clause, where_params = MoveLine._query_get()

        filters = ""

        if where_clause:
            filters = " AND " + where_clause.replace(
                'account_move_line__move_id', 'm'
            ).replace(
                'account_move_line', 'l'
            )

        # ---------------------------------------------------------
        # LOOP ACCOUNT BY ACCOUNT
        # ---------------------------------------------------------

        for account in accounts:

            move_lines = []

            initial_balance = 0.0
            debit_total = 0.0
            credit_total = 0.0
            ending_balance = 0.0

            # =====================================================
            # INITIAL BALANCE
            # =====================================================

            if init_balance:

                init_tables, init_where_clause, init_where_params = \
                    MoveLine.with_context(
                        date_from=self.env.context.get('date_from'),
                        date_to=False,
                        initial_bal=True
                    )._query_get()

                init_filters = ""

                if init_where_clause:
                    init_filters = " AND " + init_where_clause.replace(
                        'account_move_line__move_id', 'm'
                    ).replace(
                        'account_move_line', 'l'
                    )

                init_sql = """
                    SELECT
                        COALESCE(SUM(l.debit), 0.0)
                        -
                        COALESCE(SUM(l.credit), 0.0)
                    AS balance

                    FROM account_move_line l

                    JOIN account_move m
                        ON (l.move_id = m.id)

                    WHERE l.account_id = %s
                """ + init_filters

                params = (account.id,) + tuple(init_where_params)

                cr.execute(init_sql, params)

                initial_balance = cr.fetchone()[0] or 0.0

               
            # =====================================================
            # PERIOD MOVE LINES
            # =====================================================

            sql = """
                SELECT
                    l.id AS lid,
                    m.id AS move_id,
                    l.date AS ldate,
                    j.code AS lcode,
                    p.name AS partner_name,
                    l.ref AS lref,
                    m.name AS move_name,
                    l.name AS lname,
                    COALESCE(l.debit, 0.0) AS debit,
                    COALESCE(l.credit, 0.0) AS credit,
                    COALESCE(l.amount_currency, 0.0)
                        AS amount_currency,
                    c.symbol AS currency_code

                FROM account_move_line l

                JOIN account_move m
                    ON (l.move_id = m.id)

                JOIN account_journal j
                    ON (l.journal_id = j.id)

                LEFT JOIN res_partner p
                    ON (l.partner_id = p.id)

                LEFT JOIN res_currency c
                    ON (l.currency_id = c.id)

                WHERE l.account_id = %s
            """ + filters + """
                ORDER BY
            """ + sql_sort

            params = (account.id,) + tuple(where_params)

            cr.execute(sql, params)

            lines = cr.dictfetchall()

            running_balance = initial_balance

            for line in lines:

                debit_total += line['debit']
                credit_total += line['credit']

                running_balance += (
                    line['debit'] - line['credit']
                )

                line['balance'] = running_balance

                move_lines.append(line)

            ending_balance = running_balance

            # =====================================================
            # FILTERING LOGIC
            # =====================================================

            include_account = False

            if display_account == 'all':
                include_account = True

            elif display_account == 'movement':

                # IMPORTANT:
                # include if:
                # - has move lines
                # OR
                # - has opening balance

                has_real_lines = len(lines) > 0

                # include_account = (
                #     has_real_lines
                #     or
                #     not account.company_id.currency_id.is_zero(
                #         initial_balance
                #     )
                # )
                include_account = (
                    has_real_lines
                    or
                    not self.env.company.currency_id.is_zero(
                    initial_balance
                    )
                )

            elif display_account == 'not_zero':

                include_account = not self.env.company.currency_id.is_zero(
                    ending_balance
                )

            # =====================================================
            # FINAL ACCOUNT DATA
            # =====================================================

            if include_account:

                account_res.append({

                    'code': account.code,

                    'name': account.name,

                    'debit': debit_total,

                    'credit': credit_total,

                    'balance': ending_balance,

                    'initial_balance': initial_balance,

                    'ending_balance': ending_balance,

                    'move_lines': move_lines,

                })

        return account_res

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form') or not self.env.context.get('active_model'):
            raise UserError(
                _("Form content is missing, this report cannot be printed."))

        model = self.env.context.get('active_model')
        docs = self.env[model].browse(
            self.env.context.get('active_ids', []))

        init_balance = data['form'].get('initial_balance', True)
        sortby = data['form'].get('sortby', 'sort_date')
        display_account = data['form']['display_account']
        codes = []
        if data['form'].get('journal_ids', False):
            codes = [journal.code for journal in
                     self.env['account.journal'].search(
                         [('id', 'in', data['form']['journal_ids'])])]

        # accounts = docs if model == 'account.account' else self.env[
        #     'account.account'].search([])
        selected_account_ids = data['form'].get('account_ids', [])

        if selected_account_ids:
            accounts = self.env['account.account'].browse(
                selected_account_ids
            )
        else:
            accounts = docs if model == 'account.account' else self.env[
                'account.account'
            ].search([])
        accounts_res = self.with_context(
            data['form'].get('used_context', {}))._get_account_move_entry(
            accounts, init_balance, sortby, display_account)
        visible_info_columns = sum([
            data['form'].get('show_date', True),
            data['form'].get('show_journal', True),
            data['form'].get('show_partner', True),
            data['form'].get('show_ref', True),
            data['form'].get('show_move', True),
            data['form'].get('show_entry_label', True),
        ])
        return {
            'doc_ids': docids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'Accounts': accounts_res,
            'print_journal': codes,
            'visible_info_columns': visible_info_columns,
        }
