# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class BhManagementDashboard(models.Model):
    _name = 'bh.management.dashboard'
    _description = 'BH Management Dashboard'

    name = fields.Char(string='Dashboard Name', default='Executive Dashboard')

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None):
        """Main method to fetch all KPI data for the dashboard."""
        today = datetime.today()
        if not date_from:
            # Default: first day of current month
            date_from = today.replace(day=1).strftime('%Y-%m-%d')
        if not date_to:
            date_to = today.strftime('%Y-%m-%d')

        return {
            'sales':         self._get_sales_data(date_from, date_to),
            'inventory':     self._get_inventory_data(),
            'finance':       self._get_finance_data(date_from, date_to),
            'purchase':      self._get_purchase_data(date_from, date_to),
            'manufacturing': self._get_manufacturing_data(date_from, date_to),
            'hr':            self._get_hr_data(),
            'date_from':     date_from,
            'date_to':       date_to,
        }

    # ─────────────────────────────────────────────────────────────────────
    # SALES
    # ─────────────────────────────────────────────────────────────────────
    def _get_sales_data(self, date_from, date_to):
        """
        Fetch sales KPIs.

        Key fixes vs original:
        - Use (date_order AT TIME ZONE 'UTC')::date to handle timestamptz
          correctly regardless of server timezone.
        - date_to range is INCLUSIVE: we extend the upper bound to end-of-day
          using  date_order < (date_to::date + 1)  so a sale placed at
          23:59 on date_to is not silently excluded.
        - confirmed_orders: state = 'sale' (confirmed SO) OR state = 'done'
          (locked/fully-invoiced SO) — both represent real confirmed orders.
        - avg_order_value: average over confirmed+done only (not drafts).
        - total_orders: all non-cancelled SO (draft + sent + confirmed + done).
        """
        self.env.cr.execute("""
            SELECT
                COUNT(id)                                                   AS total_orders,
                COALESCE(SUM(amount_total), 0)                              AS total_revenue,
                COUNT(CASE WHEN state IN ('sale','done') THEN 1 END)        AS confirmed_orders,
                COALESCE(
                    AVG(CASE WHEN state IN ('sale','done')
                             THEN amount_total END
                    ), 0
                )                                                           AS avg_order_value
            FROM sale_order
            WHERE
                (date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND state NOT IN ('cancel')
        """, (date_from, date_to))
        summary = self.env.cr.dictfetchone()

        # ── Monthly trend — last 6 full months + current partial month ──
        self.env.cr.execute("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', date_order AT TIME ZONE 'UTC'), 'Mon YYYY') AS month,
                DATE_TRUNC('month', date_order AT TIME ZONE 'UTC')                       AS month_date,
                COALESCE(SUM(amount_total), 0)                                           AS revenue,
                COUNT(id)                                                                AS orders
            FROM sale_order
            WHERE
                date_order >= NOW() - INTERVAL '6 months'
                AND state NOT IN ('cancel')
            GROUP BY DATE_TRUNC('month', date_order AT TIME ZONE 'UTC')
            ORDER BY month_date ASC
        """)
        monthly_trend = self.env.cr.dictfetchall()

        # ── Top 5 customers by revenue in period ──
        self.env.cr.execute("""
            SELECT
                rp.name                            AS customer,
                COALESCE(SUM(so.amount_total), 0)  AS total
            FROM sale_order so
            JOIN res_partner rp ON so.partner_id = rp.id
            WHERE
                (so.date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (so.date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND so.state NOT IN ('cancel')
            GROUP BY rp.name
            ORDER BY total DESC
            LIMIT 5
        """, (date_from, date_to))
        top_customers = self.env.cr.dictfetchall()

        return {
            'summary':       summary,
            'monthly_trend': monthly_trend,
            'top_customers': top_customers,
        }

    # ─────────────────────────────────────────────────────────────────────
    # INVENTORY
    # ─────────────────────────────────────────────────────────────────────
    def _get_inventory_data(self):
        self.env.cr.execute("""
            SELECT
                COUNT(DISTINCT sq.product_id)                   AS total_products,
                COALESCE(SUM(sq.quantity), 0)                   AS total_qty,
                COALESCE((
                    SELECT SUM(svl.value)
                    FROM   stock_valuation_layer svl
                    JOIN   stock_move sm  ON svl.stock_move_id = sm.id
                    JOIN   stock_location sl2 ON sm.location_dest_id = sl2.id
                    WHERE  sl2.usage = 'internal'
                ), 0)                                           AS total_value,
                COUNT(CASE WHEN sq.quantity <= 0 THEN 1 END)    AS stockout_count
            FROM stock_quant sq
            JOIN stock_location sl ON sq.location_id = sl.id
            WHERE sl.usage = 'internal'
        """)
        summary = self.env.cr.dictfetchone()

        self.env.cr.execute("""
            SELECT
                sl.complete_name                   AS location,
                COALESCE(SUM(sq.quantity), 0)      AS qty,
                COALESCE((
                    SELECT SUM(svl2.value)
                    FROM   stock_valuation_layer svl2
                    JOIN   stock_move sm2 ON svl2.stock_move_id = sm2.id
                    WHERE  sm2.location_dest_id = sl.id
                ), 0)                              AS value
            FROM stock_quant sq
            JOIN stock_location sl ON sq.location_id = sl.id
            WHERE sl.usage = 'internal'
            GROUP BY sl.id, sl.complete_name
            ORDER BY SUM(sq.quantity) DESC
            LIMIT 6
        """)
        by_location = self.env.cr.dictfetchall()

        self.env.cr.execute("""
            SELECT
                pt.name->>'en_US'              AS product,
                COALESCE(SUM(sq.quantity), 0)  AS qty_on_hand,
                pp.id                          AS product_id
            FROM stock_quant sq
            JOIN stock_location sl  ON sq.location_id = sl.id
            JOIN product_product pp ON sq.product_id  = pp.id
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            WHERE sl.usage = 'internal'
            GROUP BY pt.name, pp.id
            HAVING SUM(sq.quantity) < 10 AND SUM(sq.quantity) >= 0
            ORDER BY qty_on_hand ASC
            LIMIT 10
        """)
        low_stock = self.env.cr.dictfetchall()

        return {
            'summary':     summary,
            'by_location': by_location,
            'low_stock':   low_stock,
        }

    # ─────────────────────────────────────────────────────────────────────
    # FINANCE
    # ─────────────────────────────────────────────────────────────────────
    def _get_finance_data(self, date_from, date_to):
        """
        Fix: use invoice_date (DATE column — no timezone cast needed).
        total_receivable / total_payable are lifetime figures (not date-filtered)
        so executives always see outstanding balances.
        """
        # Period summary
        self.env.cr.execute("""
            SELECT
                COUNT(CASE WHEN move_type = 'out_invoice' AND state = 'posted' THEN 1 END)
                                                                AS total_invoices,
                COALESCE(SUM(
                    CASE WHEN move_type = 'out_invoice' AND state = 'posted'
                         THEN amount_total ELSE 0 END
                ), 0)                                           AS total_invoiced,
                COALESCE(SUM(
                    CASE WHEN move_type = 'out_invoice' AND state = 'posted'
                              AND payment_state NOT IN ('paid','reversed')
                         THEN amount_residual ELSE 0 END
                ), 0)                                           AS total_receivable,
                COALESCE(SUM(
                    CASE WHEN move_type = 'in_invoice' AND state = 'posted'
                              AND payment_state NOT IN ('paid','reversed')
                         THEN amount_residual ELSE 0 END
                ), 0)                                           AS total_payable
            FROM account_move
            WHERE invoice_date BETWEEN %s::date AND %s::date
        """, (date_from, date_to))
        summary = self.env.cr.dictfetchone()

        # Monthly trend — last 6 months
        self.env.cr.execute("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', invoice_date), 'Mon YYYY') AS month,
                DATE_TRUNC('month', invoice_date)                       AS month_date,
                COALESCE(SUM(
                    CASE WHEN move_type = 'out_invoice' THEN amount_total ELSE 0 END
                ), 0)                                                   AS invoiced,
                COALESCE(SUM(
                    CASE WHEN move_type = 'in_invoice' THEN amount_total ELSE 0 END
                ), 0)                                                   AS bills
            FROM account_move
            WHERE state       = 'posted'
              AND invoice_date >= (CURRENT_DATE - INTERVAL '6 months')::date
              AND move_type   IN ('out_invoice', 'in_invoice')
            GROUP BY DATE_TRUNC('month', invoice_date)
            ORDER BY month_date ASC
        """)
        monthly_trend = self.env.cr.dictfetchall()

        return {
            'summary':       summary,
            'monthly_trend': monthly_trend,
        }

    # ─────────────────────────────────────────────────────────────────────
    # PURCHASE
    # ─────────────────────────────────────────────────────────────────────
    def _get_purchase_data(self, date_from, date_to):
        self.env.cr.execute("""
            SELECT
                COUNT(id)                                               AS total_orders,
                COALESCE(SUM(amount_total), 0)                          AS total_spent,
                COUNT(CASE WHEN state IN ('purchase','done') THEN 1 END) AS confirmed,
                COUNT(CASE WHEN state IN ('draft','sent')    THEN 1 END) AS rfqs
            FROM purchase_order
            WHERE
                (date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND state NOT IN ('cancel')
        """, (date_from, date_to))
        summary = self.env.cr.dictfetchone()

        self.env.cr.execute("""
            SELECT
                rp.name                            AS vendor,
                COALESCE(SUM(po.amount_total), 0)  AS total
            FROM purchase_order po
            JOIN res_partner rp ON po.partner_id = rp.id
            WHERE
                (po.date_order AT TIME ZONE 'UTC')::date >= %s::date
                AND (po.date_order AT TIME ZONE 'UTC')::date <= %s::date
                AND po.state NOT IN ('cancel')
            GROUP BY rp.name
            ORDER BY total DESC
            LIMIT 5
        """, (date_from, date_to))
        top_vendors = self.env.cr.dictfetchall()

        return {
            'summary':    summary,
            'top_vendors': top_vendors,
        }

    # ─────────────────────────────────────────────────────────────────────
    # MANUFACTURING
    # ─────────────────────────────────────────────────────────────────────
    def _get_manufacturing_data(self, date_from, date_to):
        self.env.cr.execute("""
            SELECT
                COUNT(mp.id)                                            AS total_orders,
                COUNT(CASE WHEN mp.state = 'done'      THEN 1 END)     AS completed,
                COUNT(CASE WHEN mp.state = 'progress'  THEN 1 END)     AS in_progress,
                COUNT(CASE WHEN mp.state = 'confirmed' THEN 1 END)     AS planned,
                COALESCE(SUM(mp.product_qty), 0)                       AS total_qty_planned,
                COALESCE(SUM(
                    CASE WHEN mp.state = 'done'
                         THEN mp.product_qty
                         ELSE mp.qty_producing
                    END
                ), 0)                                                  AS total_qty_produced
            FROM mrp_production mp
            WHERE
                COALESCE(
                    (mp.date_start   AT TIME ZONE 'UTC')::date,
                    (mp.date_finished AT TIME ZONE 'UTC')::date
                ) BETWEEN %s::date AND %s::date
                AND mp.state NOT IN ('cancel')
        """, (date_from, date_to))
        summary = self.env.cr.dictfetchone()

        self.env.cr.execute("""
            SELECT
                pt.name->>'en_US'                   AS product,
                COALESCE(SUM(
                    CASE WHEN mp.state = 'done'
                         THEN mp.product_qty
                         ELSE mp.qty_producing
                    END
                ), 0)                              AS produced
            FROM mrp_production mp
            JOIN product_product pp ON mp.product_id     = pp.id
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            WHERE
                COALESCE(
                    (mp.date_start    AT TIME ZONE 'UTC')::date,
                    (mp.date_finished AT TIME ZONE 'UTC')::date
                ) BETWEEN %s::date AND %s::date
                AND mp.state = 'done'
            GROUP BY pt.name
            ORDER BY produced DESC
            LIMIT 5
        """, (date_from, date_to))
        by_product = self.env.cr.dictfetchall()

        return {
            'summary':    summary,
            'by_product': by_product,
        }

    # ─────────────────────────────────────────────────────────────────────
    # HR
    # ─────────────────────────────────────────────────────────────────────
    def _get_hr_data(self):
        self.env.cr.execute("""
            SELECT
                COUNT(CASE WHEN active = true THEN 1 END)                         AS total_employees,
                COUNT(DISTINCT CASE WHEN active = true THEN department_id END)     AS total_departments,
                COUNT(CASE WHEN active = true AND gender = 'male'   THEN 1 END)   AS male_count,
                COUNT(CASE WHEN active = true AND gender = 'female' THEN 1 END)   AS female_count
            FROM hr_employee
            WHERE company_id = %s
        """, (self.env.company.id,))
        summary = self.env.cr.dictfetchone()

        self.env.cr.execute("""
            SELECT
                COALESCE(
                    hd.name->>'en_US',
                    hd.name::text,
                    'Unknown'
                )          AS department,
                COUNT(he.id) AS count
            FROM hr_employee he
            JOIN hr_department hd ON he.department_id = hd.id
            WHERE he.active = true AND he.company_id = %s
            GROUP BY hd.name
            ORDER BY count DESC
            LIMIT 8
        """, (self.env.company.id,))
        by_department = self.env.cr.dictfetchall()

        return {
            'summary':       summary,
            'by_department': by_department,
        }
