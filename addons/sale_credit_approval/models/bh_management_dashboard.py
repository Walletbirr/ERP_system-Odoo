# -*- coding: utf-8 -*-
from odoo import models


class BhManagementDashboard(models.Model):
    """Extends the Executive Dashboard (bh_management_dashboard) with a
    Credit-Approvals section, WITHOUT bh_management_dashboard depending on
    this module. sale_credit_approval already depends on
    bh_management_dashboard (see __manifest__.py), so the dependency only
    goes one way - same pattern already used for the "Credit Approvals"
    menu item in views/sale_order_approval_list_views.xml.
    """
    _inherit = 'bh.management.dashboard'

    def get_dashboard_data(self, date_from=None, date_to=None):
        data = super().get_dashboard_data(date_from=date_from, date_to=date_to)
        data['approvals'] = self._get_approvals_data()
        return data

    def _get_approvals_data(self):
        """Summary counts, a recent-requests list (Approvals tab) and the
        full set of requests the CURRENT user can act on right now
        (Sales Overview "Requests Needing Your Action" panel).

        sudo() is used the same way the rest of this dashboard uses raw SQL
        for its other KPIs: this data is only reachable by users in the
        Executive group (or admins) in the first place, via the dashboard's
        own access rules, so a wider read here doesn't leak anything a
        regular Credit-Approvals list wouldn't already show them. sudo()
        only lifts record-level access - it does NOT change self.env.user,
        so can_approve_credit below still reflects the real logged-in user.
        """
        Order = self.env['sale.order'].sudo()
        domain = [('requires_credit_approval', '=', True)]

        summary = {
            'pending': Order.search_count(domain + [('approval_state', '=', 'to_approve')]),
            'approved': Order.search_count(domain + [('approval_state', '=', 'approved')]),
            'rejected': Order.search_count(domain + [('approval_state', '=', 'rejected')]),
            'total': Order.search_count(domain),
        }

        def _row(order):
            return {
                'id': order.id,
                'name': order.name,
                'customer': order.partner_id.name or '',
                'salesperson': order.user_id.name or '',
                'amount_total': order.amount_total,
                'currency': order.currency_id.symbol or order.currency_id.name or '',
                'payment_term': order.payment_term_id.name or '',
                'state': order.approval_state,
                'submitted': order.date_order.strftime('%Y-%m-%d %H:%M') if order.date_order else '',
            }

        # Capped (not unbounded) for performance, but high enough that the
        # dashboard's search/pagination over `recent` actually has enough
        # rows to search through instead of just the last page or two.
        recent_orders = Order.search(domain, order='create_date desc', limit=200)
        recent = [_row(order) for order in recent_orders]

        # Everything currently pending, so we can filter it down to what
        # THIS user can act on. Not capped at 50 like `recent` - a request
        # should never silently vanish from "needs your action" just
        # because 50 newer (already-decided) orders piled up after it.
        pending_orders = Order.search(domain + [('approval_state', '=', 'to_approve')])
        action_required = [
            _row(order) for order in pending_orders if order.can_approve_credit
        ]

        return {
            'summary': summary,
            'recent': recent,
            'action_required': action_required,
        }
