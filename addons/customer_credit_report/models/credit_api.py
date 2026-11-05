"""Plain-data views of the credit engine for the mobile app.

Used by accounting_so_invoice_bridge (dashboard payload, approval rows and
the /bh_dashboard/mobile/credit/customer route). Everything comes from the
same records as the Odoo screens, so the app and Odoo always agree.
Amounts are in company currency; dates are 'YYYY-MM-DD' strings.
"""
from odoo import api, fields, models

HISTORY_LIMIT = 100


def _d(value):
    return fields.Date.to_string(value) if value else None


def _ageing(rec):
    return {
        'not_due': rec.amount_not_due,
        'd1_30': rec.amount_1_30,
        'd31_60': rec.amount_31_60,
        'd61_90': rec.amount_61_90,
        'd90_plus': rec.amount_90_plus,
    }


class CustomerCreditApi(models.AbstractModel):
    _name = 'customer.credit.api'
    _description = 'Customer Credit - mobile data'

    @api.model
    def overview(self, company=None, limit=200):
        """Customer Credit report: totals, ageing and who owes."""
        company = company or self.env.company
        self.env.flush_all()
        Summary = self.env['customer.credit.summary'].sudo()
        Summary.invalidate_model()
        rows = Summary.search([('company_id', '=', company.id)])
        owing = rows.filtered(lambda r: r.amount_residual > 0.005)\
            .sorted(lambda r: (-r.amount_residual, r.partner_id.name or ''))
        total = {k: sum(owing.mapped(f)) for k, f in (
            ('total_credit', 'amount_total'), ('paid', 'amount_paid'),
            ('remaining', 'amount_residual'), ('overdue', 'amount_overdue'),
            ('not_due', 'amount_not_due'), ('d1_30', 'amount_1_30'),
            ('d31_60', 'amount_31_60'), ('d61_90', 'amount_61_90'),
            ('d90_plus', 'amount_90_plus'), ('previous', 'amount_previous'))}
        pending_payments = self.env['customer.credit.payment'].sudo()\
            .search_count([('company_id', '=', company.id),
                           ('state', '=', 'submitted')])
        return {
            'configured': True,
            'currency': company.currency_id.symbol or company.currency_id.name,
            'summary': dict(
                total,
                customer_count=len(owing),
                overdue_customer_count=len(
                    owing.filtered(lambda r: r.amount_overdue > 0.005)),
                invoice_count=sum(owing.mapped('open_invoice_count')),
                unapplied=sum(rows.mapped('amount_unapplied')),
                pending_payments=pending_payments,
            ),
            'customers': [{
                'id': r.partner_id.id,
                'name': r.partner_id.name or '',
                'total_credit': r.amount_total,
                'paid': r.amount_paid,
                'remaining': r.amount_residual,
                'overdue': r.amount_overdue,
                'previous': r.amount_previous,
                'invoice_count': r.open_invoice_count,
                'max_days_overdue': r.max_days_overdue,
                'oldest_due': _d(r.oldest_due_date),
                'last_payment': _d(r.last_payment_date),
            } for r in owing[:limit]],
        }

    @api.model
    def customer_history(self, partner, company=None):
        """One customer's credit history: position, ageing, open
        invoices, all credit invoices, payments, statement, Credit Sales
        Reports and credit payments."""
        company = company or self.env.company
        partner = partner.commercial_partner_id
        self.env.flush_all()
        for model in ('customer.credit.summary', 'customer.credit.line',
                      'customer.credit.settlement'):
            self.env[model].sudo().invalidate_model()
        summary = self.env['customer.credit.summary'].sudo().search([
            ('partner_id', '=', partner.id),
            ('company_id', '=', company.id)], limit=1)
        dom = [('partner_id', '=', partner.id),
               ('company_id', '=', company.id)]
        lines = self.env['customer.credit.line'].sudo().search(
            dom, order='invoice_date desc, id desc')
        settlements = self.env['customer.credit.settlement'].sudo().search(
            dom, limit=HISTORY_LIMIT)
        statement = self.env['customer.credit.statement'].sudo()\
            ._get_statement(partner, company)
        requests = self.env['customer.credit.request'].sudo().search(
            dom + [('state', '!=', 'cancelled')], limit=20)
        payments = self.env['customer.credit.payment'].sudo().search(
            dom + [('state', 'in', ('submitted', 'posted', 'rejected'))],
            limit=20)

        def line_row(l):
            return {
                'id': l.move_id.id,
                'invoice': l.move_id.name,
                'type': l.move_type,
                'order': l.origin or '',
                'invoice_date': _d(l.invoice_date),
                'date_due': _d(l.date_due),
                'amount': l.amount_total,
                'paid': l.amount_paid,
                # paid by money in the customer's favour (part of paid)
                'covered': l.amount_covered,
                'remaining': l.amount_residual,
                'days_overdue': l.days_overdue,
                'ageing': l.ageing,
                'last_payment': _d(l.last_payment_date),
            }

        previous = lines.filtered(lambda l: l.move_type == 'previous')[:1]
        lines -= previous
        open_lines = lines.filtered(lambda l: l.is_open and
                                    l.move_type == 'out_invoice')\
            .sorted(lambda l: (l.invoice_date, l.id))
        # Payments of the previous balance (not matched to a credit sale).
        prev_payments = []
        if previous:
            Statement = self.env['customer.credit.statement'].sudo()
            entries = [e for e in Statement._previous_entries(partner, company)
                       if e['kind'] == 'previous_payment']
            moves = {m.id: m for m in self.env['account.move'].sudo().browse(
                [e['move_id'] for e in entries])}
            for e in entries:
                move = moves[e['move_id']]
                prev_payments.append({
                    'id': 'p%s' % move.id,
                    'date': _d(e['date']),
                    'invoice': None,
                    'kind': 'previous',
                    'entry': move.name,
                    'journal': move.journal_id.name or '',
                    'reference': move.ref or '',
                    'amount': -e['amount'],
                })
        stmt_lines = statement['lines'][-HISTORY_LIMIT:]
        return {
            'customer': {
                'id': partner.id,
                'name': partner.name or '',
                'phone': partner.phone or partner.mobile or '',
                'salesperson': partner.user_id.name or '',
            },
            'currency': company.currency_id.symbol or company.currency_id.name,
            'position': {
                'total_credit': summary.amount_total,
                'paid': summary.amount_paid,
                'remaining': summary.amount_residual,
                'overdue': summary.amount_overdue,
                'invoice_count': summary.invoice_count,
                'open_invoice_count': summary.open_invoice_count,
                'max_days_overdue': summary.max_days_overdue,
                'oldest_due': _d(summary.oldest_due_date),
                'first_invoice': _d(summary.first_invoice_date),
                'last_invoice': _d(summary.last_invoice_date),
                'last_payment': _d(summary.last_payment_date),
                'unapplied': summary.amount_unapplied,
                # Owed from before the first credit sale in Odoo (own
                # Credit Account); part of remaining, never overdue.
                'previous': summary.amount_previous,
                'covered': summary.amount_covered,
                'in_favour': summary.amount_unapplied,
                'previous_start': previous.amount_total if previous else 0.0,
                'previous_date': _d(previous.invoice_date)
                if previous else None,
            },
            'ageing': _ageing(summary) if summary else {
                'not_due': 0.0, 'd1_30': 0.0, 'd31_60': 0.0, 'd61_90': 0.0,
                'd90_plus': 0.0},
            'open_invoices': [line_row(l) for l in open_lines],
            'invoices': [line_row(l) for l in lines[:HISTORY_LIMIT]],
            'payments': sorted([{
                'id': s.id,
                'date': _d(s.date),
                'invoice': s.invoice_id.name,
                'kind': s.kind,
                'entry': s.payment_move_id.name,
                'journal': s.journal_id.name or '',
                'reference': s.reference or '',
                'amount': s.amount,
            } for s in settlements] + prev_payments,
                key=lambda p: p['date'] or '', reverse=True)[:HISTORY_LIMIT],
            'statement': {
                'date_from': _d(statement['date_from']),
                'date_to': _d(statement['date_to']),
                'opening': statement['opening'],
                'charged': statement['total_debit'],
                'credited': statement['total_credit'],
                'closing': statement['closing'],
                'truncated': len(statement['lines']) > len(stmt_lines),
                'lines': [{
                    'date': _d(l['date']),
                    'kind': l['kind'],
                    'label': l['kind_label'],
                    'reference': l['reference'],
                    'description': l['description'],
                    'debit': l['debit'],
                    'credit': l['credit'],
                    'balance': l['balance'],
                } for l in stmt_lines],
            },
            'credit_reports': [{
                'name': r.name,
                'order': r.sale_order_id.name,
                'date': _d(r.request_date),
                'amount': r.order_amount_company,
                'state': r.state,
                'decided_by': r.decided_by_id.name or '',
            } for r in requests],
            'credit_payments': [{
                'name': p.name,
                'date': _d(p.payment_date),
                'amount': p.amount,
                'state': p.state,
                'reference': p.reference or '',
            } for p in payments],
        }

    @api.model
    def request_payload(self, report, order=None):
        """The Credit Sales Report of an order waiting for (or decided by)
        the manager."""
        if not report:
            return None
        order = order or report.sale_order_id
        changed = bool(
            report.state == 'pending' and order
            and order.currency_id.compare_amounts(
                order.amount_total, report.order_amount) != 0)
        return {
            'name': report.name,
            'state': report.state,
            'sent_on': fields.Datetime.to_string(report.request_date)
            if report.request_date else None,
            'sent_by': report.requested_by_id.name or '',
            'note': report.note or '',
            'sales_type': report.payment_term_id.name or '',
            'order_amount': report.order_amount_company,
            'total_credit': report.credit_total,
            'paid': report.credit_paid,
            'paid_ratio': report.paid_ratio,
            'owes_now': report.credit_remaining,
            'overdue': report.credit_overdue,
            'owes_after': report.credit_after,
            'invoice_count': report.invoice_count,
            'open_invoice_count': report.open_invoice_count,
            'max_days_overdue': report.max_days_overdue,
            'first_invoice': _d(report.first_invoice_date),
            'last_payment': _d(report.last_payment_date),
            'is_new_customer': report.is_new_customer,
            'unapplied': report.amount_unapplied,
            'previous_balance': report.previous_balance,
            'ageing': _ageing(report),
            'open_invoices': [{
                'invoice': l.invoice_name,
                'order': l.origin or '',
                'invoice_date': _d(l.invoice_date),
                'date_due': _d(l.date_due),
                'amount': l.amount_total,
                'remaining': l.amount_residual,
                'days_overdue': l.days_overdue,
            } for l in report.line_ids if l.move_type != 'previous'],
            'changed_since_sent': changed,
            'decided_by': report.decided_by_id.name or '',
            'decision_note': report.decision_note or '',
            'customer_id': report.partner_id.id,
        }
