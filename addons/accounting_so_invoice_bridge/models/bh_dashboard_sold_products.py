# -*- coding: utf-8 -*-
"""Sold products for the mobile app's Commercial > Sales > "Sold Quantity" card.

Tapping that card opens a list of products with how many times each one was
sold in the selected period.

"Sold" = in how many CONFIRMED sales orders the product appears, so the same
product sold to three different customers shows once, with Sold = 3 (never as
three separate rows). The orders counted are exactly the ones behind the card
itself (state 'sale' / 'done', same date filter, same day boundaries), so the
two always agree.

Left out: section / note lines, down payments and the auto-generated "Other
Income" line - they are not products the company sold.
"""
import logging
from datetime import timedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)

PRODUCT_LIMIT = 500   # safety cap; the app pages through them 6 at a time


class BhManagementDashboardSoldProducts(models.Model):
    _inherit = 'bh.management.dashboard'

    def _get_sales_data(self, date_from, date_to):
        data = super()._get_sales_data(date_from, date_to)
        try:
            data['sold_products'] = self._get_sold_products(date_from, date_to)
        except Exception:
            # Never let this break the whole dashboard; the app then says
            # the list is not available instead of showing an empty one.
            _logger.exception(
                "accounting_so_invoice_bridge: could not build the sold "
                "products list.")
            data['sold_products'] = None
        return data

    def _get_sold_products(self, date_from, date_to):
        Line = self.env['sale.order.line'].sudo()
        start = fields.Date.to_date(date_from)
        end = fields.Date.to_date(date_to) + timedelta(days=1)  # inclusive day

        domain = [
            ('order_id.state', 'in', ('sale', 'done')),
            ('order_id.date_order', '>=', fields.Datetime.to_datetime(start)),
            ('order_id.date_order', '<', fields.Datetime.to_datetime(end)),
            ('display_type', '=', False),
            ('product_id', '!=', False),
        ]
        # Optional pieces, present only when the related modules are installed.
        if 'cim_hide_from_order_lines' in Line._fields:      # Other Income
            domain.append(('cim_hide_from_order_lines', '=', False))
        if 'is_downpayment' in Line._fields:
            domain.append(('is_downpayment', '=', False))

        groups = Line._read_group(
            domain, groupby=['product_id'],
            aggregates=['order_id:count_distinct'])

        rows = []
        for product, orders in groups:
            product = product.with_context(display_default_code=False)
            rows.append({'name': product.display_name, 'sold': orders})
        rows.sort(key=lambda r: (-r['sold'], r['name'].lower()))
        return {
            'product_count': len(rows),
            'products': rows[:PRODUCT_LIMIT],
        }