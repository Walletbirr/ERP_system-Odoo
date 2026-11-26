# -*- coding: utf-8 -*-
"""Data for the mobile app's Operations > Company tab.

    company.inventory   every product with its total and its quantity in
                        each branch (stock location of a warehouse)
    company.finance     loan / owner_withdrawal / owner_fund: one entry per
                        person with totals and a dated history

Nothing here depends on the dashboard's date filter: these screens show the
whole history, like the design ("This Month" is the current calendar month).

Everything is read with raw SQL / sudo, like the rest of the dashboard: the
Executive group has no accounting or stock rights of its own.
"""
from odoo import fields, models

HISTORY_LIMIT = 60      # newest entries kept per person
PEOPLE_LIMIT = 100


class BhManagementDashboardCompany(models.Model):
    _inherit = 'bh.management.dashboard'

    def _get_company_data(self):
        cfg = self._finance_config()
        today = fields.Date.context_today(self)
        owner = self._get_company_owner(cfg.owner_account_ids, today)
        return {
            'inventory': self._get_company_inventory(),
            'finance': {
                # Real loan records when the Employee Loan module is installed;
                # otherwise the old ledger-account reading.
                'loan': (self._get_company_loans(today)
                         if 'hr.loan' in self.env
                         else self._get_company_people(
                             cfg.loan_account_ids, 'loan', today)),
                # ONE ledger account serves both owner operations, so both
                # blocks are read from it in a single pass.
                'owner_withdrawal': owner['withdrawal'],
                'owner_fund': owner['fund'],
            },
        }

    # ------------------------------------------------------------------
    # Inventory: product -> quantity per branch
    # ------------------------------------------------------------------
    def _get_company_inventory(self):
        self.env.cr.execute("""
            SELECT sq.product_id,
                   COALESCE(sl.warehouse_id, 0) AS warehouse_id,
                   CASE WHEN sl.warehouse_id IS NULL THEN sl.id ELSE 0 END AS location_id,
                   COALESCE(SUM(sq.quantity - sq.reserved_quantity), 0) AS qty
              FROM stock_quant sq
              JOIN stock_location sl ON sl.id = sq.location_id
             WHERE sl.usage = 'internal'
             GROUP BY sq.product_id, COALESCE(sl.warehouse_id, 0),
                      CASE WHEN sl.warehouse_id IS NULL THEN sl.id ELSE 0 END
            HAVING ABS(COALESCE(SUM(sq.quantity), 0)) > 0.0001
        """)
        rows = self.env.cr.fetchall()   # read NOW, ORM reads below reuse the cursor

        Warehouse = self.env['stock.warehouse'].sudo()
        Location = self.env['stock.location'].sudo()
        Product = self.env['product.product'].sudo().with_context(
            display_default_code=False)

        labels = {}

        def label(warehouse_id, location_id):
            key = (warehouse_id, location_id)
            if key not in labels:
                if warehouse_id:
                    wh = Warehouse.browse(warehouse_id)
                    labels[key] = wh.name or wh.lot_stock_id.complete_name
                else:
                    labels[key] = Location.browse(location_id).complete_name
            return labels[key]

        per_product = {}
        for product_id, warehouse_id, location_id, qty in rows:
            branch = label(warehouse_id, location_id)
            per_product.setdefault(product_id, {})
            per_product[product_id][branch] = \
                per_product[product_id].get(branch, 0.0) + qty

        product_recs = Product.browse(list(per_product)).exists()
        names = {p.id: p.display_name for p in product_recs}
        categ_of = {p.id: p.categ_id.id for p in product_recs}
        products = []
        branches = set()
        for product_id, by_branch in per_product.items():
            if product_id not in names:
                continue
            branches.update(by_branch)
            products.append({
                'id': product_id,
                'name': names[product_id],
                'total': sum(by_branch.values()),
                'locations': sorted(
                    ({'name': name, 'qty': qty}
                     for name, qty in by_branch.items()),
                    key=lambda r: r['qty'], reverse=True),
            })
        products.sort(key=lambda p: p['total'], reverse=True)

        # Spare parts are merged into one line (the app lists them one level
        # down); every other product stays a line of its own.
        spare_categs = self._company_spare_part_category_ids()
        others, spare = self._split_spare_parts(products, categ_of, spare_categs)
        return {
            'total_qty': sum(p['total'] for p in products),
            'product_count': len(products),
            'branch_count': len(branches),
            'products': others,
            'spare_parts': ({
                'name': 'Spare Parts',
                'total': sum(p['total'] for p in spare),
                'count': len(spare),
                'products': spare,
            } if spare else None),
        }

    def _company_spare_part_category_ids(self):
        """Ids of the product categories merged into "Spare Parts": every
        product category (Inventory > Configuration > Product Categories)
        whose name contains "spare", plus its sub-categories. Nothing to
        configure: create / rename the category in Inventory and it is
        picked up. A product in "Finished Products" (or any other
        category) stays a line of its own."""
        Category = self.env['product.category'].sudo()
        roots = Category.search([('name', 'ilike', 'spare')])
        if not roots:
            return set()
        return set(Category.search([('id', 'child_of', roots.ids)]).ids)

    @staticmethod
    def _split_spare_parts(products, categ_of, spare_categ_ids):
        """(other products, spare parts), each list keeping its order."""
        others, spare = [], []
        for product in products:
            if categ_of.get(product['id']) in spare_categ_ids:
                spare.append(product)
            else:
                others.append(product)
        return others, spare

    # ------------------------------------------------------------------
    # Loans: read from the Employee Loan module (hr_employee_loan)
    # ------------------------------------------------------------------
    def _get_company_loans(self, today):
        """One entry per employee, from hr.loan / hr.loan.line.

        borrowed  = loan amounts of started loans (running + fully paid)
        paid      = installments marked paid (payslip or manual)
        remaining = borrowed - paid on running loans
        due_now   = pending installments already due (not yet deducted)
        """
        Loan = self.env['hr.loan'].sudo()
        loans = Loan.search([
            ('company_id', '=', self.env.company.id),
            ('state', 'in', ('running', 'paid')),
        ])
        people = {}
        for loan in loans:
            emp = loan.employee_id
            p = people.setdefault(emp.id, {
                'key': 'e%s' % emp.id, 'name': emp.name or '',
                'borrowed': 0.0, 'paid': 0.0, 'remaining': 0.0, 'total': 0.0,
                'due_now': 0.0, 'next_date': None, 'next_amount': 0.0,
                'on_hold': False, 'hold_reason': None,
                'loans': [], 'history': [], 'schedule': [],
            })
            running = loan.state == 'running'
            p['borrowed'] += loan.loan_amount
            p['paid'] += loan.amount_paid
            p['remaining'] += loan.amount_remaining if running else 0.0
            if running:
                reason = loan._get_hold_reason()
                if reason:
                    p['on_hold'] = True
                    p['hold_reason'] = reason
            p['loans'].append({
                'name': loan.name, 'date': loan.date.isoformat(),
                'loan_amount': loan.loan_amount,
                'installment_amount': loan.installment_amount,
                'paid': loan.amount_paid,
                'remaining': loan.amount_remaining if running else 0.0,
                'state': loan.state,
                'paid_installments': loan.paid_installments,
                'installment_count': loan.installment_count,
            })
            for line in loan.line_ids.sorted('sequence'):
                if line.state == 'paid':
                    p['history'].append({
                        'date': (line.paid_date or line.due_date).isoformat(),
                        'amount': line.amount, 'loan': loan.name,
                        'n': line.sequence, 'ref': line.payment_reference or ''})
                elif line.state in ('pending', 'skipped'):
                    p['schedule'].append({
                        'date': line.due_date.isoformat(), 'amount': line.amount,
                        'state': line.state, 'loan': loan.name, 'n': line.sequence,
                        'note': line.note or ''})
                    if line.state == 'pending' and running and line.due_date <= today:
                        p['due_now'] += line.amount

        out = []
        for p in people.values():
            p['total'] = p['borrowed']
            p['history'].sort(key=lambda h: h['date'], reverse=True)
            p['history'] = p['history'][:HISTORY_LIMIT]
            p['schedule'].sort(key=lambda r: (r['date'], r['n']))
            nxt = next((r for r in p['schedule'] if r['state'] == 'pending'), None)
            if nxt:
                p['next_date'], p['next_amount'] = nxt['date'], nxt['amount']
            p['schedule'] = p['schedule'][:24]
            out.append(p)
        out.sort(key=lambda p: (p['remaining'], p['borrowed']), reverse=True)
        out = out[:PEOPLE_LIMIT]
        borrowed = sum(p['borrowed'] for p in out)
        paid = sum(p['paid'] for p in out)
        return {
            'configured': True, 'source': 'loans', 'people': out,
            'total_borrowed': borrowed, 'total_paid': paid,
            'total_remaining': sum(p['remaining'] for p in out),
            'total_due': sum(p['due_now'] for p in out),
        }

    # ------------------------------------------------------------------
    # Finance: owner withdrawals AND owner funding (one account, two ways)
    # ------------------------------------------------------------------
    def _get_company_owner(self, accounts, today):
        """Owner Withdrawal and Owner Fund, both read from the same account.

        The accountant registers both with one "owner" account:

            withdrawal   Dr Owner account   /  Cr Bank      -> DEBIT  = money out
            fund         Dr Bank            /  Cr Owner acc. -> CREDIT = money in

        So every posted line is classified by its side, and the two actions
        are summed separately (gross, not netted against each other). Each
        person also carries the opposite total and the net.

        * One entry per owner: the Partner on the journal line, else the
          Partner of the entry, else the account itself.
        * An entry that was reversed (and its reversal) is left out, so a
          cancelled withdrawal is not counted as a fund.
        * Returns {'withdrawal': block, 'fund': block}, the shape the app's
          owner_withdrawal / owner_fund screens read.
        """
        if not accounts:
            empty = {'configured': False, 'people': [], 'total': 0.0,
                     'other_total': 0.0, 'net_total': 0.0}
            return {'withdrawal': dict(empty), 'fund': dict(empty)}

        self.env.cr.execute("""
            SELECT COALESCE(aml.partner_id, am.partner_id), aml.account_id,
                   aml.date, aml.debit, aml.credit
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE aml.account_id = ANY(%s::int[])
               AND aml.parent_state = 'posted'
               AND aml.company_id = %s
               AND aml.date <= %s::date
               AND am.reversed_entry_id IS NULL
               AND NOT EXISTS (SELECT 1 FROM account_move rev
                                WHERE rev.reversed_entry_id = am.id
                                  AND rev.state = 'posted')
             ORDER BY aml.date DESC, aml.id DESC
        """, (accounts.ids, self.env.company.id, today))
        lines = self.env.cr.fetchall()      # read NOW, ORM reads reuse the cursor

        partner_ids = {pid for pid, _a, _d, _db, _cr in lines if pid}
        partners = {p.id: p.name for p in
                    self.env['res.partner'].sudo().browse(list(partner_ids))}
        account_names = {a.id: self._clean_account_name(a.name)
                         for a in accounts.sudo()}

        month_start = today.replace(day=1)
        people = {}
        for pid, aid, date, debit, credit in lines:     # newest first
            key = ('p', pid) if pid else ('a', aid)
            person = people.setdefault(key, {
                'key': '%s%s' % key,
                'name': (partners.get(pid) if pid else None)
                        or account_names.get(aid) or '',
                'withdrawal': 0.0, 'fund': 0.0,
                'month_withdrawal': 0.0, 'month_fund': 0.0,
                'hist_withdrawal': [], 'hist_fund': [],
            })
            for action, amount in (('withdrawal', debit), ('fund', credit)):
                if not amount:
                    continue
                person[action] += amount
                if date >= month_start:
                    person['month_' + action] += amount
                person['hist_' + action].append(
                    {'date': date.isoformat(), 'amount': amount})

        def block(action, other):
            rows = []
            for p in people.values():
                total = p[action]
                if total < 0.005:
                    continue
                history = p['hist_' + action]        # newest first
                rows.append({
                    'key': p['key'], 'name': p['name'],
                    'total': total,
                    'this_month': p['month_' + action],
                    'latest_amount': history[0]['amount'],
                    'latest_date': history[0]['date'],
                    'other_total': p[other],
                    'net': total - p[other],
                    'history': history[:HISTORY_LIMIT],
                })
            rows.sort(key=lambda r: r['total'], reverse=True)
            total_all = sum(p[action] for p in people.values())
            other_all = sum(p[other] for p in people.values())
            return {'configured': True, 'people': rows[:PEOPLE_LIMIT],
                    'total': total_all, 'other_total': other_all,
                    'net_total': total_all - other_all}

        return {'withdrawal': block('withdrawal', 'fund'),
                'fund': block('fund', 'withdrawal')}

    # ------------------------------------------------------------------
    # Finance: loans (ledger-account reading, when hr.loan is not installed)
    # ------------------------------------------------------------------
    def _get_company_people(self, accounts, kind, today):
        """kind: 'loan'        borrowed = debits, paid = credits
        (Owner withdrawal / fund are read by _get_company_owner now: they
        share one account, so they are not two separate readings.)
        One entry per contact (or per account when an entry has none)."""
        empty = {'configured': bool(accounts), 'people': []}
        if kind == 'loan':
            empty.update(total_borrowed=0.0, total_paid=0.0,
                         total_remaining=0.0)
        else:
            empty.update(total=0.0)
        if not accounts:
            return empty

        self.env.cr.execute("""
            SELECT aml.partner_id, aml.account_id, aml.date,
                   aml.debit, aml.credit
              FROM account_move_line aml
             WHERE aml.account_id = ANY(%s::int[])
               AND aml.parent_state = 'posted'
               AND aml.company_id = %s
               AND aml.date <= %s::date
             ORDER BY aml.date DESC, aml.id DESC
        """, (accounts.ids, self.env.company.id, today))
        lines = self.env.cr.fetchall()

        partner_ids = {pid for pid, _a, _d, _db, _cr in lines if pid}
        partners = {p.id: p.name for p in
                    self.env['res.partner'].sudo().browse(list(partner_ids))}
        account_names = {a.id: self._clean_account_name(a.name)
                         for a in accounts.sudo()}

        month_start = today.replace(day=1)
        people = {}
        for pid, aid, date, debit, credit in lines:   # newest first
            key = ('p', pid) if pid else ('a', aid)
            person = people.setdefault(key, {
                'key': '%s%s' % key,
                'name': (partners.get(pid) if pid else None)
                        or account_names.get(aid) or '',
                'borrowed': 0.0, 'paid': 0.0, 'total': 0.0,
                'this_month': 0.0, 'history': [],
            })
            if kind == 'loan':
                person['borrowed'] += debit
                person['paid'] += credit
                if credit:
                    person['history'].append(
                        {'date': date.isoformat(), 'amount': credit})
            else:
                amount = (debit - credit) if kind == 'withdrawal' \
                    else (credit - debit)
                person['total'] += amount
                if date >= month_start:
                    person['this_month'] += amount
                if amount:
                    person['history'].append(
                        {'date': date.isoformat(), 'amount': amount})

        out = []
        for person in people.values():
            if kind == 'loan':
                person['remaining'] = person['borrowed'] - person['paid']
                if abs(person['borrowed']) < 0.005 \
                        and abs(person['paid']) < 0.005:
                    continue
                sort_value = person['borrowed']
            else:
                if abs(person['total']) < 0.005 and not person['history']:
                    continue
                # Latest real withdrawal / contribution: a reversal (negative
                # entry) stays in the history but is not "the latest".
                latest = next((h for h in person['history']
                               if h['amount'] > 0), None)
                person['latest_amount'] = latest['amount'] if latest else 0.0
                person['latest_date'] = latest['date'] if latest else None
                sort_value = person['total']
            person['history'] = person['history'][:HISTORY_LIMIT]
            person['_sort'] = sort_value
            out.append(person)
        out.sort(key=lambda p: p.pop('_sort'), reverse=True)
        out = out[:PEOPLE_LIMIT]

        result = {'configured': True, 'people': out}
        if kind == 'loan':
            borrowed = sum(p['borrowed'] for p in out)
            paid = sum(p['paid'] for p in out)
            result.update(total_borrowed=borrowed, total_paid=paid,
                          total_remaining=borrowed - paid)
        else:
            result['total'] = sum(p['total'] for p in out)
        return result