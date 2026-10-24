# -*- coding: utf-8 -*-
"""Credit sales for the mobile app's Admin > Finance > Credit tab.

Definition (same as Odoo's Customers > Invoices > "Not Paid" filter):

    a CREDIT SALE is a customer invoice that is CONFIRMED (posted) and
    not fully paid.

Draft invoices are never counted. The amount owed on an invoice is what Odoo
itself says is still open on it (amount_residual), in company currency, so a
part payment reduces it and a paid invoice drops out. Nothing here depends on
res.partner credit fields or on customer_rank.

Customers are grouped by their commercial partner, so a contact person's
invoices are added to the company they belong to.
"""
from odoo import fields, models

INVOICE_LIMIT = 300
CUSTOMER_LIMIT = 200


class BhManagementDashboardCreditSales(models.Model):
    _inherit = 'bh.management.dashboard'

    def _get_credit_sales_data(self, as_of):
        today = fields.Date.context_today(self)
        self.env.cr.execute("""
            SELECT am.id, am.name, am.invoice_date, am.invoice_date_due,
                   ABS(am.amount_total_signed)    AS total,
                   ABS(am.amount_residual_signed) AS residual,
                   cp.id, cp.name
              FROM account_move am
              JOIN res_partner p  ON p.id  = am.partner_id
              JOIN res_partner cp ON cp.id = p.commercial_partner_id
             WHERE am.move_type = 'out_invoice'
               AND am.state = 'posted'
               AND am.company_id = %s
               AND am.payment_state IN ('not_paid', 'partial')
               AND ABS(am.amount_residual_signed) > 0.005
               AND am.invoice_date <= %s::date
             ORDER BY am.invoice_date_due NULLS LAST, am.id
        """, (self.env.company.id, as_of))
        rows = self.env.cr.fetchall()

        invoices, customers = [], {}
        for _id, number, inv_date, due, total, residual, cid, cname in rows:
            late = (today - due).days if due and due < today else 0
            invoices.append({
                'number': number or '',
                'customer': cname or '',
                'date': inv_date.isoformat() if inv_date else None,
                'due': due.isoformat() if due else None,
                'total': total,
                'residual': residual,
                'days_overdue': late,
            })
            c = customers.setdefault(cid, {
                'name': cname or '', 'outstanding': 0.0, 'overdue': 0.0,
                'invoice_count': 0, 'oldest_due': None})
            c['outstanding'] += residual
            c['invoice_count'] += 1
            if late:
                c['overdue'] += residual
            if due and (c['oldest_due'] is None or due.isoformat() < c['oldest_due']):
                c['oldest_due'] = due.isoformat()

        cust_rows = sorted(customers.values(),
                           key=lambda c: c['outstanding'], reverse=True)
        return {
            'configured': True,
            'as_of': as_of,
            'summary': {
                'outstanding':    sum(i['residual'] for i in invoices),
                'invoice_count':  len(invoices),
                'overdue_amount': sum(i['residual'] for i in invoices
                                      if i['days_overdue']),
                'overdue_count':  sum(1 for i in invoices if i['days_overdue']),
                'customer_count': len(customers),
            },
            'customers': cust_rows[:CUSTOMER_LIMIT],
            'invoices': invoices[:INVOICE_LIMIT],
        }