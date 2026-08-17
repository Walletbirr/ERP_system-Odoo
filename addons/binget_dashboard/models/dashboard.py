# -*- coding: utf-8 -*-
import json
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

MONTH_LABELS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# A KPI's "previous period" figure is sometimes a tiny near-zero amount
# (e.g. one small draft order in an otherwise-quiet prior month) rather
# than a genuine zero — _pct_change's "no previous data" branch below
# only catches an *actual* zero/falsy previous, so a case like that
# still runs the division and produces a huge, meaningless swing (a few
# hundred currency units to a few million reads as a six-figure percent).
# Capping the result keeps the number readable either way: past a
# certain point the precise figure carries no extra signal, "up a lot"
# is the whole message, so this stops the KPI card text from overflowing
# or looking like a bug.
_PCT_CHANGE_CAP = 999.9


def _pct_change(current, previous):
    if not previous:
        return 100.0 if current else 0.0
    pct = round((current - previous) / abs(previous) * 100, 1)
    return max(-_PCT_CHANGE_CAP, min(_PCT_CHANGE_CAP, pct))


# ------------------------------------------------------------
# ROLE DEFINITIONS
# The dashboard's "role" is read ONLY from res.users.dashboard_role_ids
# (see models/res_users.py + models/dashboard_role.py) — never from
# Odoo's own security groups. Those two answer different questions:
# groups control what data someone can technically read or write;
# this field is a deliberate admin choice about what the DASHBOARD
# shows them. Conflating the two was the source of earlier confusion
# (e.g. Purchase staff commonly hold the basic Invoicing group just to
# post vendor bills, which technically touches accounting data without
# making them a Finance stakeholder).
#
# _ROLE_LABELS below is only used as a display fallback (e.g. building
# "<Role> Dashboard" as a title) — the actual admin-facing labels live
# on the binget.dashboard.role records themselves and can be renamed
# freely without touching this code, since only `code` is read here.
# ------------------------------------------------------------
_ROLE_LABELS = {
    "sales": "Sales",
    "purchase": "Purchase",
    "inventory": "Inventory",
    "accounting": "Finance",
    "hr": "Workforce",
    "manufacturing": "Manufacturing",
}

# Which tabs a role unlocks. `None` = always visible to everyone.
_TAB_DEFS = [
    {"key": "overview", "label": "Overview", "icon": "fa-th-large", "roles": None},
    {"key": "inventory", "label": "Inventory", "icon": "fa-cubes", "roles": {"inventory", "sales"}},
    {"key": "finance", "label": "Finance", "icon": "fa-money", "roles": {"accounting"}},
    {"key": "operations", "label": "Operations", "icon": "fa-cogs", "roles": {"purchase", "manufacturing", "hr"}},
    {"key": "activity", "label": "Activity", "icon": "fa-history", "roles": None},
]

# Which KPI tiles a role unlocks on the Overview strip.
_KPI_ROLES = {
    "revenue": {"sales", "accounting"},
    "open_orders_count": {"sales"},
    "outstanding_receivables": {"accounting"},
    "overdue_invoices_count": {"accounting"},
    "outstanding_payables": {"accounting", "purchase"},
    "open_purchase_orders": {"purchase"},
    "inventory_value": {"inventory", "sales"},
    "active_employees": {"hr"},
    "new_hires_count": {"hr"},
    "pending_time_off_count": {"hr"},
}

# The admin/executive Overview strip is deliberately NOT "every KPI from
# every role stacked together" - each role already sees their own tiles
# on their own Overview, and the role-specific tabs (Finance, Operations,
# etc.) carry the rest of that detail. Admin gets a small, top-level set:
# the five numbers an owner actually glances at first.
_ADMIN_KPIS = ["revenue", "open_orders_count", "outstanding_receivables", "inventory_value", "overdue_invoices_count"]

_ROLE_PRIORITY = ["sales", "accounting", "purchase", "inventory", "manufacturing", "hr"]

# If a section's query fails for any reason (most commonly: the viewer's
# role has read access to their own models but not another department's,
# e.g. a pure Purchase user without Sales access), get_overview() still
# returns *this* shape for that key with an "error" field added — never
# a bare {"error": ...}. The frontend always expects .rows / .stages to
# exist; without this, one inaccessible model would crash the whole
# component for that role instead of just showing an empty section.
_SECTION_DEFAULTS = {
    "kpis": {},
    "sales_trend": {"rows": []},
    "top_customers": {"rows": []},
    "top_products": {"rows": []},
    "pipeline": {"stages": [], "quote_to_order_pct": 0, "order_to_invoice_pct": 0},
    "purchase_trend": {"rows": []},
    "top_vendors": {"rows": []},
    "top_purchased_products": {"rows": []},
    "purchase_pipeline": {"stages": [], "quote_to_order_pct": 0, "order_to_invoice_pct": 0},
    "inventory_summary": {},
    "cash_flow": {"ar_aging": []},
    "top_overdue_customers": {"rows": []},
    "procurement": {},
    "workforce": {"installed": False},
    "manufacturing": {"installed": False},
    "activity": {"rows": []},
    "revenue_overview": {"labels": [], "revenue": [], "expenses": [], "total_revenue": 0, "total_expenses": 0, "net_amount": 0, "net_margin_pct": 0},
}

_CONFIG_DEFAULTS = {
    "low_stock_threshold": "5",
    "receivables_grace_days": "0",
    "velocity_window_days": "90",
    "default_period": "month",
    "show_workforce_section": "1",
    "show_manufacturing_section": "1",
    "notify_low_stock": "1",
    "notify_overdue_invoices": "1",
    "notify_pending_purchases": "1",
    "notify_orders_ready_to_invoice": "1",
}

# ------------------------------------------------------------
# PRODUCT MOVEMENT (sales-velocity) CLASSIFICATION
# Answers "does this product actually sell" alongside the stock-level
# badge (ok/low/out), which only answers "how much is left". A product
# can be "low" and still be a top seller (needs reordering urgently) or
# "low" simply because nobody buys it (doesn't matter much) — the two
# questions are independent, so this is a second, separate badge next
# to the product name rather than folded into the stock status.
#
# Ranking (not a fixed qty cutoff) is used deliberately: "sells a lot"
# only means something relative to the rest of the catalog, and a fixed
# number would need re-tuning per business. Every product that sold at
# least once in the trailing window is ranked by units sold and split
# into thirds; anything with zero sales in the window is Slow-Moving
# regardless of ranking. That's also the answer to "do we need an
# amount/quantity setting too": no — because tiers are relative
# (top/middle/bottom third of whatever sold), there's no absolute
# units-sold number to configure. The only real lever is the window
# itself (velocity_window_days, configurable in Settings) - a shorter
# window makes the ranking more reactive to recent activity, a longer
# one smooths out seasonal/bursty sales. Falls back to 90 days if the
# setting is missing, blank, zero, or not a valid number, so a bad
# value in Settings can't silently disable the classification.
# ------------------------------------------------------------
_VELOCITY_WINDOW_DAYS_DEFAULT = 90
_VELOCITY_LABELS = {
    "fast": "Fast-Moving",
    "medium": "Medium-Moving",
    "slow": "Slow-Moving",
}
_CONFIG_FLOAT_KEYS = {"low_stock_threshold", "receivables_grace_days", "velocity_window_days"}
_CONFIG_BOOL_KEYS = {"show_workforce_section", "show_manufacturing_section",
                     "notify_low_stock", "notify_overdue_invoices", "notify_pending_purchases",
                     "notify_orders_ready_to_invoice"}


class BingetDashboard(models.AbstractModel):
    """Data provider for the dashboard's OWL frontend.

    Deliberately an AbstractModel: no database table, so installing or
    upgrading this module can never fail with a migration/column error.

    DESIGN PRINCIPLES:
    1. Every section of get_overview() is wrapped in its own try/except,
       so a problem in one widget can't take down the whole dashboard.
    2. Optional integrations (Workforce, Manufacturing) are checked with
       `'model.name' in self.env` rather than a hard manifest dependency
       — this module never force-installs an app you don't already use.
    3. Role visibility is computed from the admin-managed
       binget.dashboard.role field on res.users — never from Odoo
       security groups, which answer a different question (what can
       this account technically read/write) than "what should their
       dashboard show".
    4. read_group()'s exact result-dict key names vary slightly across
       Odoo versions — every call below uses .get(key, default) rather
       than row[key] for exactly this reason.
    """
    _name = "binget.dashboard"
    _description = "Binget Dashboard Data Provider"

    # ------------------------------------------------------------
    # PERIOD HELPERS
    # ------------------------------------------------------------
    def _resolve_period(self, period, date_from, date_to):
        today = date.today()
        if period == "custom" and date_from and date_to:
            start = date.fromisoformat(date_from)
            end = date.fromisoformat(date_to)
        elif period == "quarter":
            start = today - relativedelta(months=3)
            end = today
        elif period == "year":
            start = date(today.year, 1, 1)
            end = today
        else:  # 'month' default
            start = today - relativedelta(months=1)
            end = today

        span = (end - start).days or 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span)
        return start, end, prev_start, prev_end

    def _company_domain(self, company_id):
        return [("company_id", "=", company_id)] if company_id else []

    # ------------------------------------------------------------
    # ROLE PROFILE — single source of truth for what the current user
    # is allowed to see. Read fresh every call (no caching), so an
    # admin changing someone's roles takes effect the next time that
    # person's dashboard loads — no stale state.
    # ------------------------------------------------------------
    def _is_technical_admin(self):
        # Safety net only: a real Odoo System Administrator always sees
        # everything, even before anyone has gotten around to assigning
        # them a "Full Access" dashboard role — so whoever installed
        # this module is never locked out of their own dashboard.
        try:
            return self.env.user.has_group("base.group_system")
        except Exception:
            return False

    def _get_role_profile(self):
        role_records = self.env.user.dashboard_role_ids
        codes = set(role_records.mapped("code"))

        is_admin = self._is_technical_admin() or "admin" in codes
        # "admin" is a flag, not a content section — the section codes
        # actually used to gate tabs/KPIs exclude it.
        role_set = codes - {"admin"}
        roles = sorted(role_set, key=lambda r: _ROLE_PRIORITY.index(r) if r in _ROLE_PRIORITY else 99)

        # Prefer the admin's own label for each role (so a renamed
        # "Procurement Lead" role shows as itself), falling back to the
        # generic label only if no named role record uses that code.
        record_labels = {}
        for rec in role_records:
            if rec.code and rec.code not in record_labels:
                record_labels[rec.code] = rec.name
        role_labels = [record_labels.get(r, _ROLE_LABELS.get(r, r)) for r in roles]

        visible_tabs = [
            {"key": t["key"], "label": t["label"], "icon": t["icon"]}
            for t in _TAB_DEFS
            if is_admin or t["roles"] is None or (t["roles"] & role_set)
        ]

        if is_admin:
            display_name = "Main Dashboard"
        elif roles:
            primary = next((r for r in _ROLE_PRIORITY if r in role_set), roles[0])
            display_name = "Business Dashboard" if len(roles) > 1 else f"{record_labels.get(primary, _ROLE_LABELS.get(primary, primary))} Dashboard"
        else:
            display_name = "Business Dashboard"

        if is_admin:
            visible_kpis = list(_ADMIN_KPIS)
        else:
            # No forced fallback to "revenue" here anymore - that used to
            # make an Inventory/Manufacturing-only viewer (or, until the
            # HR entries above existed, an HR viewer) see a "Revenue"
            # tile that has nothing to do with their role. A role with
            # no matching KPI tiles just gets none - the role-specific
            # widgets further down the Overview tab (or the relevant
            # tab itself) are what's actually relevant to them.
            visible_kpis = [k for k, rs in _KPI_ROLES.items() if rs & role_set]

        return {
            "is_admin": is_admin,
            "roles": roles,
            "role_labels": role_labels,
            "display_name": display_name,
            "tabs": visible_tabs,
            "visible_kpis": visible_kpis,
            "user_name": self.env.user.name,
            "has_any_role": bool(is_admin or roles),
        }

    @api.model
    def get_role_profile(self):
        return self._get_role_profile()

    # ------------------------------------------------------------
    # MAIN ENTRY POINT
    # ------------------------------------------------------------
    @api.model
    def get_overview(self, period="month", date_from=None, date_to=None, company_id=None):
        start, end, prev_start, prev_end = self._resolve_period(period, date_from, date_to)
        cid = int(company_id) if company_id else None
        profile = self._get_role_profile()
        role_set = set(profile["roles"])
        is_admin = profile["is_admin"]
        result = {}

        sections = {
            "kpis": lambda: self._get_kpis(start, end, cid),
            "sales_trend": lambda: self._get_sales_trend(start, end, cid),
            "top_customers": lambda: self._get_top_customers(start, end, cid),
            "top_products": lambda: self._get_top_products(start, end, cid),
            "pipeline": lambda: self._get_pipeline(start, end, cid),
            "purchase_trend": lambda: self._get_purchase_trend(start, end, cid),
            "top_vendors": lambda: self._get_top_vendors(start, end, cid),
            "top_purchased_products": lambda: self._get_top_purchased_products(start, end, cid),
            "purchase_pipeline": lambda: self._get_purchase_pipeline(start, end, cid),
            "inventory_summary": lambda: self._get_inventory_summary(),
            "cash_flow": lambda: self._get_cash_flow(cid),
            "top_overdue_customers": lambda: self._get_top_overdue_customers(cid),
            "procurement": lambda: self._get_procurement_snapshot(cid),
            "workforce": lambda: self._get_workforce_snapshot(),
            "manufacturing": lambda: self._get_manufacturing_snapshot(),
            "activity": lambda: self._get_recent_activity(start, end, role_set, is_admin),
            "revenue_overview": lambda: self._get_revenue_overview(start, end, cid),
        }
        for key, fn in sections.items():
            try:
                result[key] = fn()
            except Exception as e:
                result[key] = dict(_SECTION_DEFAULTS.get(key, {}), error=str(e))

        return result

    # ------------------------------------------------------------
    # EXECUTIVE KPI STRIP
    # ------------------------------------------------------------
    def _get_kpis(self, start, end, company_id):
        SaleOrder = self.env["sale.order"].sudo()
        cdomain = self._company_domain(company_id)
        params = self.env["ir.config_parameter"].sudo()

        # Deliberately just the current period's figures now - no
        # "vs last month" comparison, no trailing sparkline series.
        # Those meant computing every KPI twice (current AND previous
        # period) plus an extra weekly-bucketed history query per KPI
        # on every single Overview load - real, recurring backend work
        # for a purely decorative flourish on the card. Kept simple and
        # fast; can always be revisited later if wanted back.
        current_revenue = sum(SaleOrder.search(
            cdomain + [("state", "in", ["sale", "done"]), ("date_order", ">=", start), ("date_order", "<=", end)]
        ).mapped("amount_total"))

        open_orders = SaleOrder.search_count(cdomain + [("state", "in", ["draft", "sent"])])

        grace_days = int(float(params.get_param("binget_dashboard.receivables_grace_days", "0")))
        cutoff = date.today() - timedelta(days=grace_days)

        # A "reversed" invoice (one that's had a credit note issued
        # against it and reconciled) is a distinct payment_state in
        # Odoo, separate from paid/in_payment — but it has nothing left
        # to collect either: amount_residual is 0 the moment the credit
        # note is reconciled against it. Left out of this "not in"
        # list, it would still count as "unpaid" (and even "overdue" if
        # its due date has passed), while contributing 0 to the amount
        # total — exactly the count-vs-amount mismatch this comment is
        # here to prevent. So it's excluded everywhere receivables/
        # payables/overdue are computed, not just here.
        unpaid = self.env["account.move"].sudo().search(
            cdomain + [("move_type", "=", "out_invoice"), ("state", "=", "posted"), ("payment_state", "not in", ["paid", "in_payment", "reversed"])]
        )
        overdue = unpaid.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < cutoff)

        payable_moves = self.env["account.move"].sudo().search(
            cdomain + [("move_type", "=", "in_invoice"), ("state", "=", "posted"), ("payment_state", "not in", ["paid", "in_payment", "reversed"])]
        )
        open_pos = self.env["purchase.order"].sudo().search_count(cdomain + [("state", "in", ["draft", "sent", "to approve"])])

        threshold = float(params.get_param("binget_dashboard.low_stock_threshold", "5"))

        kpis = {
            "revenue": current_revenue,
            "open_orders_count": open_orders,
            "outstanding_receivables": sum(unpaid.mapped("amount_residual")),
            "overdue_invoices_count": len(overdue),
            "overdue_invoices_amount": sum(overdue.mapped("amount_residual")),
            "low_stock_count": self._count_low_stock(threshold),
            "outstanding_payables": sum(payable_moves.mapped("amount_residual")),
            "open_purchase_orders": open_pos,
            "inventory_value": self._get_inventory_summary()["estimated_value"],
        }

        # HR figures — soft-optional like the Manufacturing/LC blocks
        # elsewhere in this file: only computed if HR is actually
        # installed, so this dashboard has no hard dependency on it.
        if "hr.employee" in self.env:
            Employee = self.env["hr.employee"].sudo()
            active_employees = Employee.search([("active", "=", True)])

            def joined_on(emp):
                # hr.employee doesn't reliably have a dedicated "hire
                # date" field across all Odoo editions/installs, but
                # every record has create_date - close enough for "when
                # did this person show up in the system" and never
                # missing, which is what a "new hires this period" KPI
                # needs above all.
                return emp.create_date.date() if emp.create_date else None

            new_hires_current = len([e for e in active_employees if joined_on(e) and start <= joined_on(e) <= end])
            kpis["active_employees"] = len(active_employees)
            kpis["new_hires_count"] = new_hires_current

        if "hr.leave" in self.env:
            kpis["pending_time_off_count"] = self.env["hr.leave"].sudo().search_count([("state", "in", ["confirm", "validate1"])])

        return kpis

    def _count_low_stock(self, threshold):
        rows = self.env["stock.quant"].sudo().read_group([("location_id.usage", "=", "internal")], ["quantity"], ["product_id"])
        return len([r for r in rows if (r.get("quantity", 0) or 0) <= threshold])

    # ------------------------------------------------------------
    # REVENUE OVERVIEW — Revenue vs Expenses, broken into calendar
    # months across whatever range the dashboard's shared date filter
    # currently resolves to (same start/end as every other chart), not
    # pinned to "Jan through this month" regardless of that filter.
    # Revenue = posted customer invoices, Expenses = posted vendor
    # bills; both by invoice_date, mirroring how _get_cash_flow reads
    # the books elsewhere in this file.
    # ------------------------------------------------------------
    def _get_revenue_overview(self, start, end, company_id):
        cdomain = self._company_domain(company_id)
        Move = self.env["account.move"].sudo()
        multi_year = start.year != end.year

        labels, revenue, expenses = [], [], []
        cursor = date(start.year, start.month, 1)
        while cursor <= end:
            if cursor.month == 12:
                m_end = date(cursor.year, 12, 31)
            else:
                m_end = date(cursor.year, cursor.month + 1, 1) - timedelta(days=1)
            b_start = max(cursor, start)
            b_end = min(m_end, end)

            rev_moves = Move.search(cdomain + [
                ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                ("invoice_date", ">=", b_start), ("invoice_date", "<=", b_end),
            ])
            exp_moves = Move.search(cdomain + [
                ("move_type", "=", "in_invoice"), ("state", "=", "posted"),
                ("invoice_date", ">=", b_start), ("invoice_date", "<=", b_end),
            ])
            label = MONTH_LABELS_SHORT[cursor.month - 1] + (f" {cursor.year}" if multi_year else "")
            labels.append(label)
            revenue.append(sum(rev_moves.mapped("amount_total")))
            expenses.append(sum(exp_moves.mapped("amount_total")))
            cursor = cursor + relativedelta(months=1)

        total_revenue = sum(revenue)
        total_expenses = sum(expenses)
        net_amount = total_revenue - total_expenses
        net_margin_pct = round(net_amount / total_revenue * 100, 1) if total_revenue else 0.0

        return {
            "labels": labels, "revenue": revenue, "expenses": expenses,
            # Quick-glance stats for the companion "Revenue Snapshot"
            # card next to this chart — same posted-invoices/bills
            # basis as the chart itself, just for the selected period
            # as a whole instead of broken out by month.
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net_amount": net_amount,
            "net_margin_pct": net_margin_pct,
        }

    # ------------------------------------------------------------
    # SALES TREND / TOP CUSTOMERS / TOP PRODUCTS
    # ------------------------------------------------------------
    def _get_sales_trend(self, start, end, company_id):
        domain = self._company_domain(company_id) + [
            ("state", "in", ["sale", "done"]), ("date_order", ">=", start), ("date_order", "<=", end)
        ]
        groupby = "date_order:week" if (end - start).days <= 92 else "date_order:month"
        rows = self.env["sale.order"].sudo().read_group(domain, ["amount_total"], [groupby], orderby=groupby)
        return {"rows": [{"label": r.get(groupby) or "Unknown", "total": r.get("amount_total", 0) or 0} for r in rows]}

    def _get_top_customers(self, start, end, company_id, limit=5):
        domain = self._company_domain(company_id) + [
            ("state", "in", ["sale", "done"]), ("date_order", ">=", start), ("date_order", "<=", end)
        ]
        rows = self.env["sale.order"].sudo().read_group(domain, ["amount_total"], ["partner_id"], limit=limit, orderby="amount_total desc")
        return {
            "rows": [
                {"name": r.get("partner_id") and r["partner_id"][1] or "Unknown",
                 "partner_id": r.get("partner_id") and r["partner_id"][0],
                 "total": r.get("amount_total", 0) or 0}
                for r in rows
            ]
        }

    def _get_top_products(self, start, end, company_id, limit=5):
        domain = [
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", start),
            ("order_id.date_order", "<=", end),
            ("display_type", "=", False),
        ]
        if company_id:
            domain.append(("order_id.company_id", "=", company_id))
        return self._aggregate_order_lines(self.env["sale.order.line"].sudo().search(domain), limit)

    # ------------------------------------------------------------
    # SALES PIPELINE FUNNEL
    # ------------------------------------------------------------
    def _get_pipeline(self, start, end, company_id):
        SaleOrder = self.env["sale.order"].sudo()
        cdomain = self._company_domain(company_id)
        base = cdomain + [("date_order", ">=", start), ("date_order", "<=", end)]

        quotations = SaleOrder.search_count(base)
        confirmed = SaleOrder.search_count(base + [("state", "in", ["sale", "done"])])
        invoiced = SaleOrder.search_count(base + [("invoice_status", "=", "invoiced")])

        return {
            "stages": [
                {"label": "Quotations", "count": quotations},
                {"label": "Confirmed Orders", "count": confirmed},
                {"label": "Invoiced", "count": invoiced},
            ],
            "quote_to_order_pct": round((confirmed / quotations * 100), 1) if quotations else 0,
            "order_to_invoice_pct": round((invoiced / confirmed * 100), 1) if confirmed else 0,
        }

    # ------------------------------------------------------------
    # PURCHASE TREND / TOP VENDORS / TOP PURCHASED PRODUCTS — the
    # Purchase-side equivalent of the Sales widgets above, so a
    # Purchase Officer's Overview is built from their own documents,
    # not just a dimmed-down version of Sales.
    # ------------------------------------------------------------
    def _get_purchase_trend(self, start, end, company_id):
        domain = self._company_domain(company_id) + [
            ("state", "in", ["purchase", "done"]), ("date_order", ">=", start), ("date_order", "<=", end)
        ]
        groupby = "date_order:week" if (end - start).days <= 92 else "date_order:month"
        rows = self.env["purchase.order"].sudo().read_group(domain, ["amount_total"], [groupby], orderby=groupby)
        return {"rows": [{"label": r.get(groupby) or "Unknown", "total": r.get("amount_total", 0) or 0} for r in rows]}

    def _get_top_vendors(self, start, end, company_id, limit=5):
        domain = self._company_domain(company_id) + [
            ("state", "in", ["purchase", "done"]), ("date_order", ">=", start), ("date_order", "<=", end)
        ]
        rows = self.env["purchase.order"].sudo().read_group(domain, ["amount_total"], ["partner_id"], limit=limit, orderby="amount_total desc")
        return {
            "rows": [
                {"name": r.get("partner_id") and r["partner_id"][1] or "Unknown",
                 "partner_id": r.get("partner_id") and r["partner_id"][0],
                 "total": r.get("amount_total", 0) or 0}
                for r in rows
            ]
        }

    def _get_top_purchased_products(self, start, end, company_id, limit=5):
        domain = [
            ("order_id.state", "in", ["purchase", "done"]),
            ("order_id.date_order", ">=", start),
            ("order_id.date_order", "<=", end),
            ("display_type", "=", False),
        ]
        if company_id:
            domain.append(("order_id.company_id", "=", company_id))
        return self._aggregate_order_lines(self.env["purchase.order.line"].sudo().search(domain), limit)

    def _aggregate_order_lines(self, lines, limit):
        """Sum price_subtotal per product, in Python rather than a DB
        read_group keyed strictly on product_id. A plain read_group
        silently drops any line without a catalog product linked —
        which real-world purchase orders often have plenty of (a
        manually-typed fee or service line, common on LC-related
        POs). Those lines still have a real amount and a real
        description, so they're grouped by that description instead
        of being discarded."""
        totals = {}
        for line in lines:
            if line.product_id:
                key = ("product", line.product_id.id)
                name = line.product_id.display_name
                product_id = line.product_id.id
            else:
                label = (line.name or "Unspecified").splitlines()[0][:60]
                key = ("desc", label)
                name = label
                product_id = False
            if key not in totals:
                totals[key] = {"name": name, "product_id": product_id, "total": 0.0}
            totals[key]["total"] += line.price_subtotal
        rows = sorted(totals.values(), key=lambda r: r["total"], reverse=True)[:limit]
        return {"rows": rows}

    def _get_purchase_pipeline(self, start, end, company_id):
        PurchaseOrder = self.env["purchase.order"].sudo()
        cdomain = self._company_domain(company_id)
        base = cdomain + [("date_order", ">=", start), ("date_order", "<=", end)]

        rfqs = PurchaseOrder.search_count(base)
        confirmed = PurchaseOrder.search_count(base + [("state", "in", ["purchase", "done"])])
        billed = PurchaseOrder.search_count(base + [("invoice_status", "=", "invoiced")])

        return {
            "stages": [
                {"label": "RFQs", "count": rfqs},
                {"label": "Confirmed POs", "count": confirmed},
                {"label": "Billed", "count": billed},
            ],
            "quote_to_order_pct": round((confirmed / rfqs * 100), 1) if rfqs else 0,
            "order_to_invoice_pct": round((billed / confirmed * 100), 1) if confirmed else 0,
        }

    # ------------------------------------------------------------
    # INVENTORY — KPI-strip summary, branch-level rollup, a product
    # availability lookup, and a full paginated explorer table. Four
    # different granularities for four different questions.
    # ------------------------------------------------------------
    def _aggregate_quants_by_product(self, domain):
        """Groups stock.quant rows by PRODUCT, summing quantity across
        every lot/serial number (and, unless the domain already pins
        one, every location) that matches. A product tracked by unique
        serials (VINs, IMEIs, ...) has one stock.quant per unit in
        stock — without this grouping, a single product with 3 units
        on hand as 3 serials is counted, and shown, as three separate
        products instead of one product with 3 on hand."""
        quants = self.env["stock.quant"].sudo().search(domain)
        per_product = {}
        for q in quants:
            pid = q.product_id.id
            if pid not in per_product:
                per_product[pid] = {
                    "product_id": pid,
                    "product": q.product_id.display_name,
                    "quantity": 0.0,
                    "warehouses": set(),
                }
            per_product[pid]["quantity"] += q.quantity
            wh_name = q.warehouse_id.name if hasattr(q, "warehouse_id") and q.warehouse_id else None
            if wh_name:
                per_product[pid]["warehouses"].add(wh_name)
        return per_product

    def _get_velocity_window_days(self):
        raw = self.env["ir.config_parameter"].sudo().get_param("binget_dashboard.velocity_window_days", "90")
        try:
            days = int(float(raw))
        except (TypeError, ValueError):
            days = _VELOCITY_WINDOW_DAYS_DEFAULT
        return days if days > 0 else _VELOCITY_WINDOW_DAYS_DEFAULT

    def _get_product_sales_velocity(self, product_ids):
        """Units sold per product (confirmed sale order lines) in the
        trailing, admin-configurable window — the raw signal behind the
        Fast/Medium/Slow-Moving badge."""
        if not product_ids:
            return {}
        cutoff = date.today() - timedelta(days=self._get_velocity_window_days())
        domain = [
            ("product_id", "in", product_ids),
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", cutoff),
            ("display_type", "=", False),
        ]
        rows = self.env["sale.order.line"].sudo().read_group(domain, ["product_uom_qty"], ["product_id"])
        return {r["product_id"][0]: (r.get("product_uom_qty") or 0.0) for r in rows if r.get("product_id")}

    def _classify_velocity(self, product_ids):
        """Ranks the given products by trailing sales volume and splits
        them into three movement tiers. Ranking (rather than a fixed
        units-sold cutoff) is deliberate: "sells a lot" is only
        meaningful relative to the rest of the catalog, and a fixed
        number would need constant re-tuning per business. Anything
        with zero sales in the window is always Slow-Moving, regardless
        of how the rest of the catalog ranks."""
        product_ids = list(dict.fromkeys(product_ids))  # de-dupe, keep order
        velocity = self._get_product_sales_velocity(product_ids)
        selling = sorted(
            (pid for pid in product_ids if velocity.get(pid, 0) > 0),
            key=lambda pid: velocity[pid], reverse=True,
        )
        n = len(selling)
        fast_cut = -(-n // 3)       # ceil(n / 3)
        medium_cut = -(-2 * n // 3)  # ceil(2n / 3)
        tiers = {}
        for idx, pid in enumerate(selling):
            if idx < fast_cut:
                tiers[pid] = "fast"
            elif idx < medium_cut:
                tiers[pid] = "medium"
            else:
                tiers[pid] = "slow"
        for pid in product_ids:
            tiers.setdefault(pid, "slow")
        return tiers

    def _attach_velocity(self, rows):
        """Mutates a list of dicts that each have a 'product_id' key,
        adding 'velocity_tier' (fast/medium/slow) and 'velocity_label'
        (the display badge text) computed relative to the whole set of
        products passed in — not just whichever page is on screen, so
        a product's badge doesn't change depending on which page you
        paginate to."""
        tiers = self._classify_velocity([r["product_id"] for r in rows])
        for r in rows:
            tier = tiers.get(r["product_id"], "slow")
            r["velocity_tier"] = tier
            r["velocity_label"] = _VELOCITY_LABELS[tier]

    def _get_inventory_summary(self):
        threshold = float(self.env["ir.config_parameter"].sudo().get_param("binget_dashboard.low_stock_threshold", "5"))
        rows = self.env["stock.quant"].sudo().read_group([("location_id.usage", "=", "internal")], ["quantity"], ["product_id"])
        out_of_stock = sum(1 for r in rows if (r.get("quantity", 0) or 0) <= 0)
        low_stock = sum(1 for r in rows if 0 < (r.get("quantity", 0) or 0) <= threshold)

        # Rough valuation estimate using each product's standard cost —
        # an operational estimate, not a formal accounting valuation
        # (which would need landed cost / FIFO layers this module has
        # no visibility into).
        quants = self.env["stock.quant"].sudo().search([("location_id.usage", "=", "internal"), ("quantity", ">", 0)])
        value = sum(q.quantity * (q.product_id.standard_price or 0) for q in quants)

        return {
            "total_sku_count": len(rows),
            "out_of_stock_count": out_of_stock,
            "low_stock_count": low_stock,
            "estimated_value": value,
            "threshold": threshold,
        }

    @api.model
    def get_inventory_branches(self):
        """Branch/warehouse-level rollup — answers 'how is each branch
        doing' at a glance, as cards rather than an empty filter
        dropdown with nothing selected under it."""
        threshold = float(self.env["ir.config_parameter"].sudo().get_param("binget_dashboard.low_stock_threshold", "5"))
        warehouses = self.env["stock.warehouse"].sudo().search([])
        rows = []
        for wh in warehouses:
            if not wh.view_location_id:
                continue
            quants = self.env["stock.quant"].sudo().search([
                ("location_id", "child_of", wh.view_location_id.id),
                ("location_id.usage", "=", "internal"),
            ])
            per_product = {}
            for q in quants:
                per_product[q.product_id.id] = per_product.get(q.product_id.id, 0) + q.quantity
            low = sum(1 for qty in per_product.values() if 0 < qty <= threshold)
            out = sum(1 for qty in per_product.values() if qty <= 0)
            value = sum(q.quantity * (q.product_id.standard_price or 0) for q in quants if q.quantity > 0)
            rows.append({
                "id": wh.id,
                "name": wh.name,
                "company": wh.company_id.name,
                "sku_count": len(per_product),
                "low_stock": low,
                "out_of_stock": out,
                "estimated_value": value,
            })
        rows.sort(key=lambda r: r["name"])
        return {"rows": rows}

    @api.model
    def get_branch_detail(self, warehouse_id, limit=8):
        """Rich single-branch summary for the branch-card drill-down
        modal: the same rollup as the card, plus the specific items at
        that branch that actually need attention (low/out), so opening
        a branch answers 'what should I do about it', not just 'what
        are the totals'."""
        warehouse = self.env["stock.warehouse"].sudo().browse(int(warehouse_id))
        if not warehouse.exists() or not warehouse.view_location_id:
            return {"found": False}

        threshold = float(self.env["ir.config_parameter"].sudo().get_param("binget_dashboard.low_stock_threshold", "5"))
        base_domain = [
            ("location_id", "child_of", warehouse.view_location_id.id),
            ("location_id.usage", "=", "internal"),
        ]
        quants = self.env["stock.quant"].sudo().search(base_domain)
        per_product = {}
        for q in quants:
            per_product[q.product_id.id] = per_product.get(q.product_id.id, 0) + q.quantity
        low = sum(1 for qty in per_product.values() if 0 < qty <= threshold)
        out = sum(1 for qty in per_product.values() if qty <= 0)
        value = sum(q.quantity * (q.product_id.standard_price or 0) for q in quants if q.quantity > 0)

        # PRODUCT-level, not one row per stock.quant — see
        # _aggregate_quants_by_product: a product tracked by unique
        # lot/serial numbers (e.g. VINs) would otherwise show up here
        # as several separate "needs attention" rows instead of one.
        per_product_agg = self._aggregate_quants_by_product(base_domain)
        attention_data = sorted(
            (d for d in per_product_agg.values() if d["quantity"] <= threshold),
            key=lambda d: d["quantity"],
        )[:limit]
        self._attach_velocity(attention_data)
        attention_rows = [{
            "product_id": d["product_id"],
            "product": d["product"],
            "quantity": d["quantity"],
            "status": "out" if d["quantity"] <= 0 else "low",
            "velocity_tier": d["velocity_tier"],
            "velocity_label": d["velocity_label"],
        } for d in attention_data]

        return {
            "found": True,
            "id": warehouse.id,
            "name": warehouse.name,
            "company": warehouse.company_id.name,
            "sku_count": len(per_product),
            "low_stock": low,
            "out_of_stock": out,
            "estimated_value": value,
            "attention_rows": attention_rows,
        }

    @api.model
    def get_product_availability(self, query, limit=8):
        """'Where is this product available' lookup — searches by name
        or reference and returns per-branch quantities, instead of
        making the user pick from an unfiltered product dropdown."""
        query = (query or "").strip()
        if len(query) < 2:
            return {"rows": []}
        products = self.env["product.product"].sudo().search(
            ["|", ("name", "ilike", query), ("default_code", "ilike", query)], limit=limit
        )
        results = []
        for p in products:
            quants = self.env["stock.quant"].sudo().search([
                ("product_id", "=", p.id), ("location_id.usage", "=", "internal"),
            ])
            by_branch = {}
            for q in quants:
                label = q.warehouse_id.name if q.warehouse_id else (q.location_id.display_name or "Unassigned")
                by_branch[label] = by_branch.get(label, 0) + q.quantity
            total_qty = sum(by_branch.values())
            results.append({
                "product_id": p.id,
                "name": p.display_name,
                "reference": p.default_code or "",
                "total_qty": total_qty,
                "branches": [{"name": k, "quantity": v} for k, v in sorted(by_branch.items()) if v],
            })
        return {"rows": results}

    @api.model
    def get_inventory_explorer(self, warehouse_id=None, location_id=None, product_id=None, status=None, limit=50, offset=0):
        """Full filterable/paginated inventory table, separate from the
        overview call since this can be a large dataset on a real
        install and shouldn't slow down the main dashboard load.

        Rows are PRODUCT-level, not one row per stock.quant: a product
        tracked by unique lot/serial numbers (e.g. VINs) has one quant
        per unit in stock, and a per-quant listing would show that
        single product as several separate rows — each individually
        judged "low"/"out" off just its own unit — instead of one
        product with its combined quantity on hand. Status filtering
        and pagination therefore both happen in Python, after
        aggregating, rather than as a search domain on stock.quant.
        """
        domain = [("location_id.usage", "=", "internal")]
        if location_id:
            domain.append(("location_id", "=", int(location_id)))
        elif warehouse_id:
            warehouse = self.env["stock.warehouse"].sudo().browse(int(warehouse_id))
            if warehouse.view_location_id:
                domain.append(("location_id", "child_of", warehouse.view_location_id.id))
        if product_id:
            domain.append(("product_id", "=", int(product_id)))

        threshold = float(self.env["ir.config_parameter"].sudo().get_param("binget_dashboard.low_stock_threshold", "5"))
        per_product = self._aggregate_quants_by_product(domain)

        rows = []
        for data in per_product.values():
            qty = data["quantity"]
            row_status = "out" if qty <= 0 else ("low" if qty <= threshold else "ok")
            if status and status not in ("all",) and status != row_status:
                continue
            rows.append({
                "product_id": data["product_id"],
                "product": data["product"],
                "warehouse": ", ".join(sorted(data["warehouses"])) if data["warehouses"] else "",
                "quantity": data["quantity"],
                "status": row_status,
            })
        rows.sort(key=lambda r: r["quantity"])

        total = len(rows)
        page_rows = rows[offset:offset + limit]
        self._attach_velocity(page_rows)
        return {"rows": page_rows, "total": total}

    @api.model
    def get_filter_options(self):
        locations = self.env["stock.location"].sudo().search_read([("usage", "=", "internal")], ["id", "display_name"], limit=200, order="display_name")
        warehouses = self.env["stock.warehouse"].sudo().search_read([], ["id", "name"], order="name")
        companies = self.env["res.company"].sudo().search_read([], ["id", "name"], order="name")
        return {
            "locations": [{"id": location["id"], "name": location["display_name"]} for location in locations],
            "warehouses": [{"id": w["id"], "name": w["name"]} for w in warehouses],
            "companies": [{"id": c["id"], "name": c["name"]} for c in companies],
        }

    # ------------------------------------------------------------
    # CASH FLOW — Receivables (AR) + Payables (AP) + aging, together
    # ------------------------------------------------------------
    def _aging_buckets(self, moves):
        today = date.today()
        buckets = {"Current": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
        for m in moves:
            residual = m.amount_residual
            due = m.invoice_date_due
            if not due or due >= today:
                buckets["Current"] += residual
                continue
            overdue_days = (today - due).days
            if overdue_days <= 30:
                buckets["1-30"] += residual
            elif overdue_days <= 60:
                buckets["31-60"] += residual
            elif overdue_days <= 90:
                buckets["61-90"] += residual
            else:
                buckets["90+"] += residual
        return [{"label": k, "amount": v} for k, v in buckets.items()]

    def _get_cash_flow(self, company_id):
        cdomain = self._company_domain(company_id)
        receivable_moves = self.env["account.move"].sudo().search(
            cdomain + [("move_type", "=", "out_invoice"), ("state", "=", "posted"), ("payment_state", "not in", ["paid", "in_payment", "reversed"])]
        )
        payable_moves = self.env["account.move"].sudo().search(
            cdomain + [("move_type", "=", "in_invoice"), ("state", "=", "posted"), ("payment_state", "not in", ["paid", "in_payment", "reversed"])]
        )
        total_receivable = sum(receivable_moves.mapped("amount_residual"))
        total_payable = sum(payable_moves.mapped("amount_residual"))
        return {
            "total_receivable": total_receivable,
            "total_payable": total_payable,
            "net_position": total_receivable - total_payable,
            "ar_aging": self._aging_buckets(receivable_moves),
        }

    def _get_top_overdue_customers(self, company_id, limit=5):
        """The Finance-role equivalent of Top Customers: not who bought
        the most, but who owes the most past their due date — a
        collections worklist, which is what an accountant actually
        needs at a glance rather than sales volume."""
        cdomain = self._company_domain(company_id)
        overdue = self.env["account.move"].sudo().search(
            cdomain + [
                ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                ("payment_state", "not in", ["paid", "in_payment", "reversed"]),
                ("invoice_date_due", "<", date.today()),
            ]
        )
        totals = {}
        for move in overdue:
            partner = move.partner_id
            key = partner.id
            if key not in totals:
                totals[key] = {"name": partner.name or "Unknown", "partner_id": partner.id, "total": 0.0}
            totals[key]["total"] += move.amount_residual
        rows = sorted(totals.values(), key=lambda r: r["total"], reverse=True)[:limit]
        return {"rows": rows}

    # ------------------------------------------------------------
    # PROCUREMENT
    # ------------------------------------------------------------
    def _get_procurement_snapshot(self, company_id):
        PurchaseOrder = self.env["purchase.order"].sudo()
        cdomain = self._company_domain(company_id)
        return {
            "draft_count": PurchaseOrder.search_count(cdomain + [("state", "=", "draft")]),
            "pending_count": PurchaseOrder.search_count(cdomain + [("state", "in", ["sent", "to approve"])]),
            "confirmed_count": PurchaseOrder.search_count(cdomain + [("state", "=", "purchase")]),
            "open_amount": sum(PurchaseOrder.search(cdomain + [("state", "in", ["draft", "sent", "purchase"])]).mapped("amount_total")),
        }

    # ------------------------------------------------------------
    # WORKFORCE (soft-optional — only if HR is actually installed, and
    # only computed if the admin hasn't turned the section off)
    # ------------------------------------------------------------
    def _get_workforce_snapshot(self):
        show = self.env["ir.config_parameter"].sudo().get_param("binget_dashboard.show_workforce_section", "1") in ("1", "true", "True")
        if not show or "hr.employee" not in self.env:
            return {"installed": False}
        Employee = self.env["hr.employee"].sudo()
        active = Employee.search([("active", "=", True)])
        result = {"installed": True, "active_employees": len(active)}
        if "hr.leave" in self.env:
            result["pending_time_off"] = self.env["hr.leave"].sudo().search_count([("state", "in", ["confirm", "validate1"])])
        else:
            result["pending_time_off"] = None

        # Department Distribution — active headcount per department,
        # for a pie chart on the HR Overview tab. Employees without a
        # department land in "Unassigned" rather than silently
        # vanishing from the total (a pie chart that doesn't add up to
        # the headcount number above it looks broken).
        dept_counts = {}
        for emp in active:
            label = emp.department_id.name or "Unassigned"
            dept_counts[label] = dept_counts.get(label, 0) + 1
        result["department_distribution"] = [
            {"label": k, "count": v} for k, v in sorted(dept_counts.items(), key=lambda kv: -kv[1])
        ]

        # Employee Growth — cumulative active headcount at the end of
        # each of the last 6 months, using create_date as the "joined"
        # moment (see the same choice/reasoning in _get_kpis above).
        # Cumulative rather than "hires per month" so the line actually
        # shows growth (or shrinkage) of the team over time, the way
        # Sales Trend shows revenue over time.
        today = date.today()
        month_starts = []
        cursor = today.replace(day=1)
        for _ in range(6):
            month_starts.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        month_starts.reverse()

        join_dates = sorted(d for d in (
            (e.create_date.date() if e.create_date else None) for e in active
        ) if d)

        growth = []
        for m_start in month_starts:
            next_month = (m_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_end = next_month - timedelta(days=1)
            count = sum(1 for d in join_dates if d <= month_end)
            growth.append({"label": m_start.strftime("%b"), "count": count})
        result["employee_growth"] = growth

        return result

    # ------------------------------------------------------------
    # MANUFACTURING (soft-optional — only if Manufacturing is installed)
    # ------------------------------------------------------------
    def _get_manufacturing_snapshot(self):
        show = self.env["ir.config_parameter"].sudo().get_param("binget_dashboard.show_manufacturing_section", "1") in ("1", "true", "True")
        if not show or "mrp.production" not in self.env:
            return {"installed": False}
        MO = self.env["mrp.production"].sudo()
        in_progress = MO.search_count([("state", "=", "progress")])
        late = MO.search_count([("state", "not in", ["done", "cancel"]), ("date_deadline", "<", date.today())])
        return {"installed": True, "in_progress": in_progress, "late": late}

    # ------------------------------------------------------------
    # RECENT ACTIVITY — unified across Sales, Invoices, Purchases, and
    # Manufacturing, filtered both by what the viewer's role covers
    # (so a Purchase Officer doesn't scroll past sales-order noise)
    # AND, for anyone who isn't a full-access admin, to records they
    # themselves created — this is "your recent activity", not a feed
    # of everyone else's in the same department.
    # ------------------------------------------------------------
    def _get_recent_activity(self, start, end, role_set, is_admin, limit=10):
        """Deliberately just a role-filtered slice of _build_activity_rows
        - see that method's docstring. This used to be its own,
        separate query (only 4 of the 7+ tracked types, its own domain
        construction) which is exactly how it drifted out of sync with
        the Activity Log tab - the same user's own data could show up
        in one and not the other. Sharing the builder makes that
        structurally impossible going forward: whatever Activity Log
        can see, this is always a subset of, never a divergent copy.
        include_updates=False here on purpose - see the builder's
        docstring for why."""
        scope_user = None if is_admin else self.env.uid
        rows = self._build_activity_rows(
            scope_user=scope_user, company_id=None,
            date_from=start, date_to=end,
            type_filter=None, search=None, include_updates=False,
        )
        if not is_admin:
            rows = [r for r in rows if role_set & self._ACTIVITY_TYPE_ROLES.get(r["type_key"], set())]
        rows.sort(key=lambda r: r["date"] or "", reverse=True)
        activity = [{
            "type": r["type"], "label": r["label"], "partner": r["partner"],
            "amount": r["amount"], "date": r["date"], "res_id": r["res_id"], "model": r["model"],
        } for r in rows[:limit]]
        return {"rows": activity}

    # ------------------------------------------------------------
    # ACTIVITY LOG — the full, searchable/filterable counterpart to the
    # short Recent Activity widget above. Two kinds of rows now:
    #   - "created": the document itself was created (as before)
    #   - "updated": a field on the document was changed after the
    #     fact — sourced from Odoo's own change-tracking (chatter),
    #     so this is genuinely "every change that user made", not
    #     just the moment they hit Save on a new record.
    #   Other invariants unchanged:
    #   - not capped to a handful of rows — paginated
    #   - not gated by dashboard role — this is "everything you did",
    #     an audit trail, not role-relevant department content
    #   - non-admins are hard-locked to their own records regardless of
    #     what user_id the client sends; only an admin can look at
    #     someone else's activity, or everyone's at once
    # ------------------------------------------------------------
    _ACTIVITY_PER_TYPE_CAP = 300

    # Models whose edits are surfaced as "updated" rows, alongside the
    # existing four "created" document types. Kept to an intentional,
    # business-relevant list rather than every mail.thread model in the
    # database (settings, internal technical models, etc.) so the log
    # stays a readable audit trail instead of engineering noise.
    _ACTIVITY_TRACKED_MODELS = {
        "sale.order": "sale_order",
        "account.move": None,  # split into invoice/bill below by move_type
        "purchase.order": "purchase_order",
        "mrp.production": "manufacturing_order",
        "stock.picking": "stock_picking",
        "res.partner": "contact",
        "product.template": "product",
        "hr.employee": "employee",
    }

    # Which Dashboard Role(s) a given activity type_key is relevant to,
    # for the Recent Activity widget only (see _get_recent_activity) -
    # the full Activity Log tab ignores this entirely and shows a
    # non-admin every type of their own activity, unfiltered by role,
    # since that tab is a personal audit trail, not department content.
    # A type_key not listed here (there currently are none) would be
    # admin-only in Recent Activity.
    _ACTIVITY_TYPE_ROLES = {
        "sale_order": {"sales"},
        "invoice": {"accounting"},
        "bill": {"accounting"},
        "purchase_order": {"purchase"},
        "manufacturing_order": {"manufacturing"},
        "stock_picking": {"inventory", "manufacturing"},
        "contact": {"sales", "purchase"},
        "product": {"sales", "inventory", "purchase"},
        "employee": {"hr"},
    }

    def _tracking_field_value(self, tv, old):
        """Human-readable string for one side (old/new) of a single
        mail.tracking.value, based on the tracked field's type."""
        ttype = tv.field_id.ttype
        suffix = "old_value_" if old else "new_value_"
        if ttype == "boolean":
            return "Yes" if tv[suffix + "integer"] else "No"
        if ttype == "monetary":
            return "{:,.2f}".format(tv[suffix + "float"])
        if ttype == "date":
            val = tv[suffix + "datetime"]
            return val.date().isoformat() if val else ""
        if ttype == "datetime":
            val = tv[suffix + "datetime"]
            return fields.Datetime.to_string(val) if val else ""
        if ttype == "float":
            val = tv[suffix + "float"]
            return ("{:.2f}".format(val)).rstrip("0").rstrip(".") or "0"
        if ttype == "integer":
            return str(tv[suffix + "integer"])
        if ttype in ("char", "text", "selection", "many2one", "many2many", "one2many"):
            return tv[suffix + "char"] or (tv[suffix + "text"] if ttype == "text" else "") or ""
        return tv[suffix + "char"] or ""

    def _tracking_message_change_text(self, tvs):
        """One combined 'Field: old → new; Field2: old2 → new2' summary
        for every tracked field changed within a single write (message)."""
        parts = []
        for tv in tvs:
            if not tv.field_id:
                continue
            label = tv.field_id.field_description or tv.field_id.name
            old_v = self._tracking_field_value(tv, True)
            new_v = self._tracking_field_value(tv, False)
            parts.append("%s: %s → %s" % (label, old_v or "—", new_v or "—"))
        return "; ".join(parts)

    def _record_company_id(self, model, res_id):
        """Best-effort company_id of a record, for company filtering of
        'updated' rows. Returns None if the model has no company_id or
        the record no longer exists."""
        if model not in self.env:
            return None
        Model = self.env[model].sudo()
        if "company_id" not in Model._fields:
            return None
        rec = Model.browse(res_id)
        if not rec.exists():
            return None
        return rec.company_id.id or None

    def _get_activity_updates(self, models, scope_user, start, end, company_id, search_l, matches):
        """'Updated' rows: one per write (mail.message), covering every
        field changed in that write, across the given models.

        Deliberately two explicit queries (mail.message first, then
        mail.tracking.value filtered by those message ids) rather than
        one dotted-path domain like [("mail_message_id.create_uid",
        "=", scope_user)] on mail.tracking.value directly. Functionally
        the same result, but this way each step is independently
        loggable - when a non-admin's activity log comes back missing
        rows an admin can clearly see, this tells you exactly where it
        drops out: no matching messages at all (points at create_uid on
        the message itself, e.g. a write done through an automation/
        different technical user), or messages found but no tracking
        values attached (points at the field not being marked
        tracking=True, or a write that didn't actually change a
        tracked field's stored value)."""
        cap = self._ACTIVITY_PER_TYPE_CAP
        rows = []
        for model in models:
            if model not in self.env:
                continue
            try:
                msg_domain = [("model", "=", model)]
                if scope_user:
                    msg_domain.append(("create_uid", "=", scope_user))
                if start:
                    msg_domain.append(("create_date", ">=", start))
                if end:
                    msg_domain.append(("create_date", "<=", end))
                messages = self.env["mail.message"].sudo().search(msg_domain, order="create_date desc", limit=cap * 3)
                if not messages:
                    if scope_user:
                        _logger.info(
                            "binget_dashboard: 0 mail.message rows for scope_user=%s model=%s in %s..%s (domain=%s) "
                            "- no matching message at all, so no tracking values to even look for. If this user "
                            "definitely edited a %s in this window, check who create_uid is on that record's "
                            "actual mail.message (Settings > Technical > Messages, filtered by model/res_id) - if "
                            "it's not this uid, the edit was recorded under a different account (e.g. an "
                            "automation, a related write, or a stale login session).",
                            scope_user, model, start, end, msg_domain, model,
                        )
                    continue

                tvs = self.env["mail.tracking.value"].sudo().search(
                    [("mail_message_id", "in", messages.ids)], order="mail_message_id desc", limit=cap * 3
                )
                if not tvs:
                    if scope_user:
                        _logger.info(
                            "binget_dashboard: %d matching mail.message rows for scope_user=%s model=%s, but 0 "
                            "mail.tracking.value rows attached to any of them - the message(s) exist (e.g. a "
                            "chatter note or a plain 'created' log) but no tracked field's value actually "
                            "changed, or the field that changed isn't marked tracking=True on this model.",
                            len(messages), scope_user, model,
                        )
                    continue

                if scope_user:
                    _logger.debug(
                        "binget_dashboard: %d messages / %d tracking values for scope_user=%s model=%s",
                        len(messages), len(tvs), scope_user, model,
                    )

                by_message = {}
                for tv in tvs:
                    by_message.setdefault(tv.mail_message_id, self.env["mail.tracking.value"])
                    by_message[tv.mail_message_id] |= tv

                count = 0
                for message, message_tvs in by_message.items():
                    if count >= cap:
                        break
                    if company_id and self._record_company_id(model, message.res_id) not in (None, int(company_id)):
                        continue
                    change_text = self._tracking_message_change_text(message_tvs)
                    if not change_text:
                        continue
                    label = message.record_name or ""
                    if not matches(label, change_text):
                        continue

                    type_key = self._ACTIVITY_TRACKED_MODELS.get(model)
                    type_label = self._model_label(model)
                    if model == "account.move":
                        move = self.env["account.move"].sudo().browse(message.res_id)
                        is_bill = move.move_type == "in_invoice"
                        type_key = "bill" if is_bill else "invoice"
                        type_label = "Bill" if is_bill else "Invoice"

                    rows.append({
                        "action": "updated", "type": type_label, "type_key": type_key, "label": label,
                        "partner": "", "amount": 0, "change": change_text,
                        "date": message.create_date and message.create_date.isoformat(),
                        "res_id": message.res_id, "model": model, "user": message.create_uid.name or "",
                    })
                    count += 1
            except Exception:
                # One model's tracking data (e.g. a field type this
                # method doesn't expect) no longer takes every other
                # model down with it - see _tracking_field_value.
                _logger.exception("binget_dashboard: activity 'updated' rows failed for model %s", model)
        return rows

    _MODEL_LABEL_CACHE = {}

    def _model_label(self, model):
        if model not in self._MODEL_LABEL_CACHE:
            imodel = self.env["ir.model"].sudo().search([("model", "=", model)], limit=1)
            self._MODEL_LABEL_CACHE[model] = imodel.name if imodel else model
        return self._MODEL_LABEL_CACHE[model]

    @api.model
    def get_activity_users(self):
        """Populates the admin-only 'user' filter dropdown. Empty list
        for non-admins — they never see this control at all."""
        if not self._get_role_profile()["is_admin"]:
            return {"rows": []}
        users = self.env["res.users"].sudo().search([("share", "=", False), ("active", "=", True)], order="name")
        return {"rows": [{"id": u.id, "name": u.name} for u in users]}

    @api.model
    def get_activity_debug(self, user_id, date_from=None, date_to=None, company_id=None):
        """Admin-only, on-screen version of the server-log diagnostic
        added alongside this: for the given user, shows exactly how
        many mail.message / mail.tracking.value rows exist per tracked
        model, with create_uid on the single most recent one of each -
        so 'the dashboard doesn't know who did it' can be checked
        directly on screen instead of needing server log access.

        date_from/date_to/company_id are OPTIONAL and used only for
        the second live-method column below (run with your actual
        current dashboard filters) - every other number in this method
        deliberately ignores them, to answer 'does the data exist for
        this user at all' before even asking whether today's filters
        happen to exclude it."""
        if not self._get_role_profile()["is_admin"]:
            raise AccessError("Admins only.")
        target = self.env["res.users"].sudo().browse(int(user_id))
        if not target.exists():
            raise AccessError("That user no longer exists.")

        end_bound = f"{date_to} 23:59:59" if date_to else None

        results = []
        for model in self._ACTIVITY_TRACKED_MODELS:
            if model not in self.env:
                continue
            created_count = self.env[model].sudo().search_count([("create_uid", "=", target.id)])

            own_messages = self.env["mail.message"].sudo().search(
                [("model", "=", model), ("create_uid", "=", target.id)], order="create_date desc", limit=1
            )
            own_message_count = self.env["mail.message"].sudo().search_count(
                [("model", "=", model), ("create_uid", "=", target.id)]
            )
            all_messages_this_model = self.env["mail.message"].sudo().search_count([("model", "=", model)])

            own_tv_count = 0
            latest_tv_message_creator = ""
            if own_message_count:
                own_tv_count = self.env["mail.tracking.value"].sudo().search_count(
                    [("mail_message_id.model", "=", model), ("mail_message_id.create_uid", "=", target.id)]
                )
            latest_any_tv = self.env["mail.tracking.value"].sudo().search(
                [("mail_message_id.model", "=", model)], order="mail_message_id desc", limit=1
            )
            if latest_any_tv:
                latest_tv_message_creator = latest_any_tv.mail_message_id.create_uid.name or ""

            # Two calls into the EXACT method the real Activity Log
            # uses (_get_activity_updates): one with no date/company
            # narrowing at all ("does the code path work on this data,
            # period"), one with whatever filters your dashboard is
            # actually showing right now ("does it work under today's
            # actual conditions"). Any exception either hits is
            # surfaced here instead of silently logged-and-swallowed
            # the way it is in the real call (see _build_activity_rows).
            live_rows_unfiltered = live_error_unfiltered = None
            try:
                live_rows_unfiltered = len(self._get_activity_updates(
                    [model], target.id, None, None, None, "", lambda *texts: True,
                ))
            except Exception as exc:
                live_error_unfiltered = f"{type(exc).__name__}: {exc}"

            live_rows_current = live_error_current = None
            if date_from or date_to or company_id:
                try:
                    live_rows_current = len(self._get_activity_updates(
                        [model], target.id, date_from, end_bound, company_id, "", lambda *texts: True,
                    ))
                except Exception as exc:
                    live_error_current = f"{type(exc).__name__}: {exc}"

            results.append({
                "model": model,
                "label": self._model_label(model),
                "created_by_user": created_count,
                "messages_by_user": own_message_count,
                "messages_total_this_model": all_messages_this_model,
                "tracking_values_by_user": own_tv_count,
                "live_rows_from_real_method": live_rows_unfiltered,
                "live_error": live_error_unfiltered,
                "live_rows_current_filters": live_rows_current,
                "live_error_current_filters": live_error_current,
                "latest_message_sample": {
                    "res_id": own_messages.res_id if own_messages else None,
                    "date": own_messages.create_date.isoformat() if own_messages else None,
                } if own_messages else None,
                "latest_tracking_value_creator_anywhere": latest_tv_message_creator,
            })

        return {
            "user": target.name, "user_id": target.id, "results": results,
            "filters_used": {"date_from": date_from, "date_to": date_to, "company_id": company_id},
        }

    @api.model
    def get_activity_log(self, type_filter=None, user_id=None, search=None,
                          date_from=None, date_to=None, company_id=None, limit=25, offset=0):
        is_admin = self._get_role_profile()["is_admin"]

        # The single most important line in this method: a non-admin can
        # never see anyone's activity but their own, no matter what the
        # client sends as user_id.
        scope_user = self.env.uid if not is_admin else (int(user_id) if user_id else None)

        rows = self._build_activity_rows(
            scope_user=scope_user, company_id=company_id,
            date_from=date_from, date_to=date_to,
            type_filter=type_filter, search=search,
        )
        rows.sort(key=lambda r: r["date"] or "", reverse=True)
        total = len(rows)
        return {"rows": rows[offset:offset + limit], "total": total}

    def _build_activity_rows(self, scope_user, company_id, date_from, date_to,
                              type_filter=None, search=None, include_updates=True):
        """The single source of truth for 'what did this user do' -
        both get_activity_log (the full, paginated Activity Log tab)
        and _get_recent_activity (the small Overview widget) build
        their rows from this SAME method, so the two can never again
        silently drift apart the way they used to (Recent Activity only
        covering 4 of the 7+ tracked types, its own separate domain
        construction, etc.) - Recent Activity is now, structurally, a
        role-filtered slice of exactly what this returns, not a
        parallel implementation of its own. Unsorted, uncapped-by-
        pagination - callers sort/paginate/role-filter as they need.

        scope_user=None means "everyone" (admin only, ever - callers
        are responsible for never passing None for a non-admin).

        include_updates=False skips the chatter/tracking-based
        "updated" rows entirely (the more expensive half of this
        method, scanning mail.message/mail.tracking.value) - used by
        the Overview widget, which reloads on every dashboard visit and
        has no business carrying that cost just to show a handful of
        recent rows; the full Activity Log tab always wants it."""
        domain = []
        if scope_user:
            domain.append(("create_uid", "=", scope_user))
        if company_id:
            domain.append(("company_id", "=", int(company_id)))
        if date_from:
            domain.append(("create_date", ">=", date_from))
        if date_to:
            domain.append(("create_date", "<=", f"{date_to} 23:59:59"))

        search_l = (search or "").strip().lower()

        def matches(*texts):
            if not search_l:
                return True
            return any(search_l in (t or "").lower() for t in texts)

        rows = []
        cap = self._ACTIVITY_PER_TYPE_CAP

        # Each block below is independently wrapped: previously a single
        # bad record (e.g. a partner with a broken related field, or a
        # model quirk on one company's data) raised out of this whole
        # method and get_activity_log came back empty with NO error
        # surfaced anywhere the user could see - it just looked exactly
        # like "no activity", indistinguishable from a genuinely empty
        # result, even though Recent Activity (a separate, narrower
        # query) kept working fine. Logging + skipping the one broken
        # type means the other 7 still show up, and the log line gives
        # an admin something to actually search for instead of a user
        # reporting "activity log is broken" with no lead at all.
        if type_filter in (None, "all", "sale_order"):
            try:
                for so in self.env["sale.order"].sudo().search(domain, order="create_date desc", limit=cap):
                    if matches(so.name, so.partner_id.name):
                        rows.append({"action": "created", "change": "Created", "type": "Sales Order", "type_key": "sale_order", "label": so.name,
                                     "partner": so.partner_id.name or "", "amount": so.amount_total,
                                     "date": so.create_date and so.create_date.isoformat(),
                                     "res_id": so.id, "model": "sale.order", "user": so.create_uid.name or ""})
            except Exception:
                _logger.exception("binget_dashboard: activity log failed building 'sale.order' rows")

        if type_filter in (None, "all", "invoice", "bill"):
            try:
                move_types = {"invoice": ["out_invoice"], "bill": ["in_invoice"]}.get(type_filter, ["out_invoice", "in_invoice"])
                for inv in self.env["account.move"].sudo().search(domain + [("move_type", "in", move_types)], order="create_date desc", limit=cap):
                    is_bill = inv.move_type == "in_invoice"
                    if matches(inv.name, inv.partner_id.name):
                        rows.append({"action": "created", "change": "Created", "type": "Bill" if is_bill else "Invoice", "type_key": "bill" if is_bill else "invoice",
                                     "label": inv.name, "partner": inv.partner_id.name or "", "amount": inv.amount_total,
                                     "date": inv.create_date and inv.create_date.isoformat(),
                                     "res_id": inv.id, "model": "account.move", "user": inv.create_uid.name or ""})
            except Exception:
                _logger.exception("binget_dashboard: activity log failed building 'account.move' rows")

        if type_filter in (None, "all", "purchase_order"):
            try:
                for po in self.env["purchase.order"].sudo().search(domain, order="create_date desc", limit=cap):
                    if matches(po.name, po.partner_id.name):
                        rows.append({"action": "created", "change": "Created", "type": "Purchase Order", "type_key": "purchase_order", "label": po.name,
                                     "partner": po.partner_id.name or "", "amount": po.amount_total,
                                     "date": po.create_date and po.create_date.isoformat(),
                                     "res_id": po.id, "model": "purchase.order", "user": po.create_uid.name or ""})
            except Exception:
                _logger.exception("binget_dashboard: activity log failed building 'purchase.order' rows")

        if type_filter in (None, "all", "manufacturing_order") and "mrp.production" in self.env:
            try:
                for mo in self.env["mrp.production"].sudo().search(domain, order="create_date desc", limit=cap):
                    if matches(mo.name, ""):
                        rows.append({"action": "created", "change": "Created", "type": "Manufacturing Order", "type_key": "manufacturing_order", "label": mo.name,
                                     "partner": "", "amount": 0,
                                     "date": mo.create_date and mo.create_date.isoformat(),
                                     "res_id": mo.id, "model": "mrp.production", "user": mo.create_uid.name or ""})
            except Exception:
                _logger.exception("binget_dashboard: activity log failed building 'mrp.production' rows")

        if type_filter in (None, "all", "stock_picking") and "stock.picking" in self.env:
            try:
                for pk in self.env["stock.picking"].sudo().search(domain, order="create_date desc", limit=cap):
                    if matches(pk.name, pk.partner_id.name):
                        rows.append({"action": "created", "change": "Created", "type": "Transfer", "type_key": "stock_picking", "label": pk.name,
                                     "partner": pk.partner_id.name or "", "amount": 0,
                                     "date": pk.create_date and pk.create_date.isoformat(),
                                     "res_id": pk.id, "model": "stock.picking", "user": pk.create_uid.name or ""})
            except Exception:
                _logger.exception("binget_dashboard: activity log failed building 'stock.picking' rows")

        if type_filter in (None, "all", "contact"):
            try:
                for p in self.env["res.partner"].sudo().search(domain, order="create_date desc", limit=cap):
                    if matches(p.name, ""):
                        rows.append({"action": "created", "change": "Created", "type": "Contact", "type_key": "contact", "label": p.name or "",
                                     "partner": "", "amount": 0,
                                     "date": p.create_date and p.create_date.isoformat(),
                                     "res_id": p.id, "model": "res.partner", "user": p.create_uid.name or ""})
            except Exception:
                _logger.exception("binget_dashboard: activity log failed building 'res.partner' rows")

        if type_filter in (None, "all", "product"):
            try:
                for pt in self.env["product.template"].sudo().search(domain, order="create_date desc", limit=cap):
                    if matches(pt.name, ""):
                        rows.append({"action": "created", "change": "Created", "type": "Product", "type_key": "product", "label": pt.name or "",
                                     "partner": "", "amount": 0,
                                     "date": pt.create_date and pt.create_date.isoformat(),
                                     "res_id": pt.id, "model": "product.template", "user": pt.create_uid.name or ""})
            except Exception:
                _logger.exception("binget_dashboard: activity log failed building 'product.template' rows")

        # "Employee" - added specifically because plain hr.employee
        # creation (e.g. onboarding someone through the Employees app)
        # previously had no "created" row anywhere at all, admin or not
        # - res.partner alone only covers the case where a bare Contact
        # is created directly, not an Employee record.
        if type_filter in (None, "all", "employee") and "hr.employee" in self.env:
            try:
                for emp in self.env["hr.employee"].sudo().search(domain, order="create_date desc", limit=cap):
                    if matches(emp.name, ""):
                        rows.append({"action": "created", "change": "Created", "type": "Employee", "type_key": "employee", "label": emp.name or "",
                                     "partner": "", "amount": 0,
                                     "date": emp.create_date and emp.create_date.isoformat(),
                                     "res_id": emp.id, "model": "hr.employee", "user": emp.create_uid.name or ""})
            except Exception:
                _logger.exception("binget_dashboard: activity log failed building 'hr.employee' rows")

        # "Updated" rows — every field change (not just the initial
        # creation) on the same set of business models, sourced from
        # Odoo's own chatter tracking. This is what makes the log "every
        # change made by that user", not only the documents they started.
        # "Deleted" rows - the one action type that can't come from
        # chatter (a removed record has no chatter left to scan), so it
        # reads the standalone deletion log instead. Included regardless
        # of include_updates - deletions are cheap to query (one simple
        # table, no mail.tracking.value join) and, unlike edits, are
        # exactly the kind of thing Recent Activity should surface too.
        try:
            del_domain = []
            if scope_user:
                del_domain.append(("user_id", "=", scope_user))
            if company_id:
                del_domain.append(("company_id", "=", int(company_id)))
            if date_from:
                del_domain.append(("delete_date", ">=", date_from))
            if date_to:
                del_domain.append(("delete_date", "<=", f"{date_to} 23:59:59"))
            if type_filter not in (None, "all"):
                del_domain.append(("type_key", "=", type_filter))
            for d in self.env["binget.dashboard.activity.deletion"].sudo().search(del_domain, order="delete_date desc", limit=cap):
                if matches(d.label, d.partner):
                    rows.append({
                        "action": "deleted", "change": "Deleted", "type": d.type_label, "type_key": d.type_key,
                        "label": d.label or "", "partner": d.partner or "", "amount": d.amount,
                        "date": d.delete_date and d.delete_date.isoformat(),
                        "res_id": d.res_id, "model": d.res_model, "user": d.user_id.name or "",
                    })
        except Exception:
            _logger.exception("binget_dashboard: activity log failed building 'deleted' rows")

        if not include_updates:
            return rows

        filter_to_models = {
            "sale_order": ["sale.order"], "invoice": ["account.move"], "bill": ["account.move"],
            "purchase_order": ["purchase.order"], "manufacturing_order": ["mrp.production"],
            "stock_picking": ["stock.picking"], "contact": ["res.partner"], "product": ["product.template"],
            "employee": ["hr.employee"],
        }
        if type_filter in (None, "all"):
            update_models = list(self._ACTIVITY_TRACKED_MODELS.keys())
        else:
            update_models = filter_to_models.get(type_filter, [])
        update_models = [m for m in update_models if m in self.env]

        end_bound = f"{date_to} 23:59:59" if date_to else None
        try:
            rows.extend(self._get_activity_updates(update_models, scope_user, date_from, end_bound, company_id, search_l, matches))
        except Exception:
            # Same reasoning as the try/except blocks above: the
            # "created" rows gathered so far are still returned even if
            # the (more expensive, chatter-scanning) "updated" half
            # blows up on some record.
            _logger.exception("binget_dashboard: activity log failed building 'updated' rows")

        return rows

    # ------------------------------------------------------------
    # ACTIVITY LOG PDF EXPORT — admin only, enforced here (not just
    # hidden in the UI) since this is the actual data source the PDF
    # renders from. Reads whichever filters were active in the Activity
    # Log at export time via the action context (see dashboard.js's
    # exportActivityPdf), re-runs the exact same query get_activity_log
    # uses (uncapped, up to a generous ceiling) so the PDF matches what
    # was on screen.
    #
    # NOTE: this is named _activity_report_values, not Odoo's magic
    # _get_report_values — that magic name only gets picked up by the
    # report engine on a model literally called
    # "report.<module>.<template_id>" (here: report.binget_dashboard.
    # activity_report_document). Defining it directly on binget.dashboard
    # would silently never be called, and the PDF would render with
    # every field blank - which is exactly the bug this split avoids.
    # See BingetDashboardActivityReport below, which is that model and
    # just delegates back to this method.
    # ------------------------------------------------------------
    _ACTIVITY_TYPE_LABELS = {
        "all": "All Types", "sale_order": "Sales Orders", "invoice": "Invoices",
        "bill": "Bills", "purchase_order": "Purchase Orders", "manufacturing_order": "Manufacturing Orders",
        "stock_picking": "Inventory Transfers", "contact": "Contacts", "product": "Products",
        "employee": "Employees",
    }

    def _activity_report_values(self, docids, data=None):
        if not self._get_role_profile()["is_admin"]:
            raise AccessError("Only administrators can export the Activity Log.")

        ctx = self.env.context
        type_filter = ctx.get("binget_activity_type_filter") or "all"
        user_id = ctx.get("binget_activity_user_id")
        search = ctx.get("binget_activity_search")
        date_from = ctx.get("binget_activity_date_from")
        date_to = ctx.get("binget_activity_date_to")
        company_id = ctx.get("binget_activity_company_id")

        result = self.get_activity_log(
            type_filter=type_filter, user_id=user_id, search=search,
            date_from=date_from, date_to=date_to, company_id=company_id,
            limit=2000, offset=0,
        )

        user_label = "All Users"
        if user_id:
            user = self.env["res.users"].sudo().browse(int(user_id))
            user_label = user.name or "All Users"

        return {
            "doc_ids": docids,
            "doc_model": "binget.dashboard",
            "rows": result["rows"],
            "total": result["total"],
            "type_label": self._ACTIVITY_TYPE_LABELS.get(type_filter, "All Types"),
            "user_label": user_label,
            "date_from": date_from,
            "date_to": date_to,
            "search": search,
            "generated_by": self.env.user.name,
            "generated_at": fields.Datetime.context_timestamp(self, fields.Datetime.now()),
            "company_name": self.env.company.name,
        }

    # ------------------------------------------------------------
    # NOTIFICATIONS — role-aware, actionable alerts, each togglable
    # from Settings. Computed fresh on every call (no stored state to
    # go stale), and only surfaced to the roles the item is actually
    # relevant to.
    # ------------------------------------------------------------
    @api.model
    def get_notifications(self):
        profile = self._get_role_profile()
        role_set = set(profile["roles"])
        is_admin = profile["is_admin"]
        params = self.env["ir.config_parameter"].sudo()
        notifications = []

        def flag(key):
            return params.get_param(f"binget_dashboard.{key}", "1") in ("1", "true", "True")

        if (is_admin or "accounting" in role_set) and flag("notify_overdue_invoices"):
            grace_days = int(float(params.get_param("binget_dashboard.receivables_grace_days", "0")))
            cutoff = date.today() - timedelta(days=grace_days)
            overdue = self.env["account.move"].sudo().search([
                ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                ("payment_state", "not in", ["paid", "in_payment", "reversed"]),
                ("invoice_date_due", "<", cutoff),
            ])
            if overdue:
                notifications.append({
                    "id": "overdue_invoices", "severity": "critical", "notif_type": "system",
                    "title": f"{len(overdue)} overdue invoice(s)",
                    "description": f"{sum(overdue.mapped('amount_residual')):,.0f} past due",
                    "action": "openOverdueInvoices",
                })

        if (is_admin or "inventory" in role_set or "sales" in role_set) and flag("notify_low_stock"):
            threshold = float(params.get_param("binget_dashboard.low_stock_threshold", "5"))
            low = self._count_low_stock(threshold)
            if low:
                notifications.append({
                    "id": "low_stock", "severity": "warning", "notif_type": "system",
                    "title": f"{low} product(s) low or out of stock",
                    "description": "Review inventory levels",
                    "action": "openLowStock",
                })

        if (is_admin or "purchase" in role_set) and flag("notify_pending_purchases"):
            pending = self.env["purchase.order"].sudo().search_count([("state", "in", ["sent", "to approve"])])
            if pending:
                notifications.append({
                    "id": "pending_purchases", "severity": "info", "notif_type": "system",
                    "title": f"{pending} purchase order(s) awaiting approval",
                    "description": "Review the procurement queue",
                    "action": "openPendingPurchases",
                })

        # Sales Orders confirmed and awaiting an invoice - Accounting's
        # side of the accounting_so_invoice_bridge module's Sales <->
        # Accounting handoff (see that module for the full flow: a
        # confirmed order, optionally with a submitted payment-proof
        # file attached, sitting in invoice_status "to invoice" until
        # someone in Accounting creates the invoice). Soft integration
        # only - accounting_so_invoice_bridge is not a hard dependency
        # of this module, so the extra "payment proof submitted" filter
        # (and the corresponding wording) is only applied when that
        # module's field is actually present; without it, this still
        # works as a plain "confirmed, not yet invoiced" count.
        if (is_admin or "accounting" in role_set) and "sale.order" in self.env and flag("notify_orders_ready_to_invoice"):
            so_fields = self.env["sale.order"]._fields
            domain = [("state", "=", "sale"), ("invoice_status", "=", "to invoice")]
            proof_aware = "x_has_submitted_payment_proof" in so_fields
            if proof_aware:
                domain.append(("x_has_submitted_payment_proof", "=", True))
            ready = self.env["sale.order"].sudo().search_count(domain)
            if ready:
                notifications.append({
                    "id": "orders_ready_to_invoice", "severity": "info", "notif_type": "system",
                    "title": f"{ready} sales order(s) confirmed and ready to invoice",
                    "description": (
                        "Payment proof submitted - create the invoice when ready"
                        if proof_aware else
                        "Confirmed and awaiting invoicing"
                    ),
                    "action": "openOrdersReadyToInvoice",
                })

        if (is_admin or "hr" in role_set) and "hr.leave" in self.env:
            pending_to = self.env["hr.leave"].sudo().search_count([("state", "in", ["confirm", "validate1"])])
            if pending_to:
                notifications.append({
                    "id": "pending_time_off", "severity": "info", "notif_type": "system",
                    "title": f"{pending_to} time off request(s) pending",
                    "description": "Review workforce requests",
                    "action": "openTimeOff",
                })

        # LC Management integration — soft-optional, same pattern as HR/
        # Manufacturing above: this dashboard has no hard dependency on
        # that module, so it's only checked if actually installed. Shown
        # to whoever the request is specifically assigned to (an
        # accountant doesn't need to see every other accountant's queue),
        # plus admins.
        #
        # Every LC notification below is notif_type "request", including
        # the admin-oversight fallback branches: this is still a real,
        # named request sitting in someone's queue waiting on a concrete
        # status change (account created / payment approved / LC opened)
        # - not a generic system FYI like overdue invoices or low stock.
        # So it behaves the same for admins as for the assigned
        # accountant: acknowledging it only clears it from the badge, it
        # keeps showing in the list, and it never times out - it's only
        # gone once that status actually changes.
        if "lc.account.setup.request" in self.env:
            own_pending = self.env["lc.account.setup.request"].sudo().search_count([
                ("assigned_accountant_id", "=", self.env.uid),
                ("state", "!=", "completed"),
            ])
            if own_pending:
                notifications.append({
                    "id": "lc_account_requests", "severity": "warning", "notif_type": "request",
                    "title": f"{own_pending} LC account request(s) assigned to you",
                    "description": "A Purchase Officer needs a GL account set up",
                    "action": "openLCAccountRequests",
                })
            elif is_admin:
                all_pending = self.env["lc.account.setup.request"].sudo().search_count([("state", "!=", "completed")])
                if all_pending:
                    notifications.append({
                        "id": "lc_account_requests", "severity": "info", "notif_type": "request",
                        "title": f"{all_pending} LC account request(s) outstanding",
                        "description": "Awaiting an accountant to set up the GL account",
                        "action": "openLCAccountRequests",
                    })

        # LC Management — settlement payment approval requests. Same
        # per-accountant scoping as the account-setup block above: a
        # Purchase Officer picks exactly one accountant when sending the
        # request (lc.settlement.line.assigned_accountant_id), so only
        # that accountant (plus admins, as a fallback so nothing silently
        # goes unnoticed) sees it here.
        if "lc.settlement.line" in self.env:
            own_payment_pending = self.env["lc.settlement.line"].sudo().search_count([
                ("assigned_accountant_id", "=", self.env.uid),
                ("state", "=", "submitted"),
            ])
            if own_payment_pending:
                notifications.append({
                    "id": "lc_payment_requests", "severity": "warning", "notif_type": "request",
                    "title": f"{own_payment_pending} LC payment request(s) awaiting your approval",
                    "description": "A Purchase Officer submitted a settlement payment for review",
                    "action": "openLCPaymentRequests",
                })
            elif is_admin:
                all_payment_pending = self.env["lc.settlement.line"].sudo().search_count([("state", "=", "submitted")])
                if all_payment_pending:
                    notifications.append({
                        "id": "lc_payment_requests", "severity": "info", "notif_type": "request",
                        "title": f"{all_payment_pending} LC payment request(s) outstanding",
                        "description": "Awaiting an accountant to review and approve",
                        "action": "openLCPaymentRequests",
                    })

        # LC Management — opening-approval requests (the Purchase Officer's
        # "Request LC Opening" step). Same per-accountant scoping again:
        # lc.management.opening_assigned_accountant_id holds the one
        # accountant chosen when the request was sent.
        if "lc.management" in self.env:
            own_opening_pending = self.env["lc.management"].sudo().search_count([
                ("opening_assigned_accountant_id", "=", self.env.uid),
                ("state", "=", "pending_approval"),
            ])
            if own_opening_pending:
                notifications.append({
                    "id": "lc_opening_requests", "severity": "warning", "notif_type": "request",
                    "title": f"{own_opening_pending} LC opening request(s) awaiting your approval",
                    "description": "A Purchase Officer requested this LC be opened",
                    "action": "openLCOpeningRequests",
                })
            elif is_admin:
                all_opening_pending = self.env["lc.management"].sudo().search_count([("state", "=", "pending_approval")])
                if all_opening_pending:
                    notifications.append({
                        "id": "lc_opening_requests", "severity": "info", "notif_type": "request",
                        "title": f"{all_opening_pending} LC opening request(s) outstanding",
                        "description": "Awaiting an accountant to review and open",
                        "action": "openLCOpeningRequests",
                    })

        # "New since you last acknowledged it" — the two notif_types
        # behave differently on purpose:
        #
        #  REQUEST rows (assigned specifically to this user - LC account/
        #  opening/payment approvals) represent one concrete piece of
        #  work someone is waiting on. They should NOT come back and
        #  re-alert on a timer just because a few days passed - that's
        #  noise, not a system problem. Once seen, a request row stays
        #  quiet (is_new goes False, so it stops counting toward the
        #  badge) but keeps showing in the list until it's genuinely
        #  resolved (at which point it simply stops being generated at
        #  all - see the LC blocks above). It only flips back to "new"
        #  if the underlying count actually changes (e.g. a second
        #  request comes in while the first is still pending).
        #
        #  SYSTEM rows (overdue invoices, low stock, admin-oversight
        #  FYIs, …) are the dashboard itself nudging someone about a
        #  standing issue nobody owns personally. Those genuinely should
        #  keep nagging periodically if left unresolved - every
        #  _SYSTEM_RENOTIFY_DAYS days they reappear in the list, add
        #  back to the badge, and need to be acknowledged again.
        try:
            seen_map = json.loads(self.env.user.dashboard_seen_notifications or "{}")
        except (ValueError, TypeError):
            seen_map = {}
        now = fields.Datetime.now()
        for n in notifications:
            entry = seen_map.get(n["id"])
            if not entry:
                n["is_new"] = True
                continue
            # Backward-compat: older records stored the seen title as a
            # plain string with no timestamp.
            if isinstance(entry, str):
                n["is_new"] = entry != n["title"]
                continue
            if entry.get("title") != n["title"]:
                n["is_new"] = True
                continue
            if n["notif_type"] == "system":
                seen_on = fields.Datetime.from_string(entry.get("seen_on")) if entry.get("seen_on") else None
                n["is_new"] = bool(
                    not seen_on or (now - seen_on) >= timedelta(days=self._SYSTEM_RENOTIFY_DAYS)
                )
            else:
                # Request rows: seen is seen. No timer - stays quiet
                # until the count itself changes (handled above) or it
                # gets resolved and stops being generated entirely.
                n["is_new"] = False

        return {"rows": notifications}

    # How often an unresolved SYSTEM alert re-surfaces after being
    # acknowledged. Deliberately does not apply to REQUEST rows - see
    # the comment above.
    _SYSTEM_RENOTIFY_DAYS = 7

    def _seen_entry(self, n):
        return {"title": n["title"], "seen_on": fields.Datetime.to_string(fields.Datetime.now())}

    @api.model
    def mark_notifications_seen(self):
        """Record the current notifications as acknowledged for this
        user. Deliberately does not touch the underlying data those
        notifications describe — an overdue invoice marked "seen" is
        still overdue, it just stops counting toward the badge. System
        alerts also drop out of the list entirely until either the
        underlying count changes or _SYSTEM_RENOTIFY_DAYS pass with it
        still unresolved. Request rows (assigned to this user) never
        re-alert on a timer - they just keep showing, quietly, until
        actually resolved."""
        current = self.get_notifications()["rows"]
        seen_map = {n["id"]: self._seen_entry(n) for n in current}
        self.env.user.sudo().write({"dashboard_seen_notifications": json.dumps(seen_map)})
        return True

    @api.model
    def mark_notification_seen(self, notif_id, notif_title):
        """Acknowledge a single notification by id, leaving every other
        row's seen-state untouched."""
        try:
            seen_map = json.loads(self.env.user.dashboard_seen_notifications or "{}")
        except (ValueError, TypeError):
            seen_map = {}
        seen_map[notif_id] = self._seen_entry({"title": notif_title})
        self.env.user.sudo().write({"dashboard_seen_notifications": json.dumps(seen_map)})
        return True

    # ------------------------------------------------------------
    # CONFIGURATION — admin-only writes, everyone can read (needed to
    # know e.g. the low-stock threshold that's already coloring badges
    # they can see).
    # ------------------------------------------------------------
    @api.model
    def get_config(self):
        params = self.env["ir.config_parameter"].sudo()
        out = {}
        for key, default in _CONFIG_DEFAULTS.items():
            raw = params.get_param(f"binget_dashboard.{key}", default)
            if key in _CONFIG_FLOAT_KEYS:
                out[key] = float(raw)
            elif key in _CONFIG_BOOL_KEYS:
                out[key] = raw in ("1", "true", "True")
            else:
                out[key] = raw
        out["is_admin"] = self._get_role_profile()["is_admin"]
        return out

    @api.model
    def set_config(self, key, value):
        if key not in _CONFIG_DEFAULTS:
            return False
        if not self._get_role_profile()["is_admin"]:
            raise AccessError("Only administrators can change dashboard settings.")
        self.env["ir.config_parameter"].sudo().set_param(f"binget_dashboard.{key}", str(value))
        return True


class BingetDashboardActivityReport(models.AbstractModel):
    # Odoo's QWeb report engine looks specifically for a model named
    # "report.<report_name>" (report_name being the template's xml id,
    # "binget_dashboard.activity_report_document") and calls
    # _get_report_values on THAT model - it does not matter that the
    # ir.actions.report record's own `model` field says binget.dashboard.
    # This class exists purely to satisfy that convention; all the real
    # logic lives in binget.dashboard._activity_report_values so it stays
    # next to get_activity_log, which it mirrors.
    _name = "report.binget_dashboard.activity_report_document"
    _description = "Binget Dashboard – Activity Log PDF"

    def _get_report_values(self, docids, data=None):
        return self.env["binget.dashboard"]._activity_report_values(docids, data=data)
