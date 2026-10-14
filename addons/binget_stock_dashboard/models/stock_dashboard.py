# -*- coding: utf-8 -*-
from odoo import api, models


class BingetStockDashboard(models.AbstractModel):
    """Live data provider for the Binget Stock Dashboard (Odoo 18)."""
    _name = 'binget.stock.dashboard'
    _description = 'Binget Stock Dashboard'

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------
    @api.model
    def get_overview(self):
        warehouses = self.env['stock.warehouse'].search([], order='sequence, id')
        warehouse_cards = [self._get_warehouse_stats(wh) for wh in warehouses]

        total_units = sum(c['units'] for c in warehouse_cards)
        total_value = sum(c['value'] for c in warehouse_cards)
        total_low_stock = sum(c['low_stock'] for c in warehouse_cards)
        total_out = sum(c['out_of_stock'] for c in warehouse_cards)
        total_incoming = sum(c['incoming'] for c in warehouse_cards)
        total_outgoing = sum(c['outgoing'] for c in warehouse_cards)

        all_products = self.env['product.product'].search_count([
            ('is_storable', '=', True),
            ('active', '=', True),
        ])

        all_card = {
            'id': 0,
            'name': 'All Warehouses',
            'location': 'All Locations',
            'products': all_products,
            'units': total_units,
            'value': total_value,
            'incoming': total_incoming,
            'outgoing': total_outgoing,
            'low_stock': total_low_stock,
            'out_of_stock': total_out,
            'good_stock': max(0, all_products - total_low_stock),
        }

        return {
            'kpis': {
                'total_warehouses': len(warehouses),
                'total_products': all_products,
                'total_units': total_units,
                'total_value': total_value,
                'low_stock_items': total_low_stock,
            },
            'all_warehouses_card': all_card,
            'warehouses': warehouse_cards,
            'currency_symbol': self.env.company.currency_id.symbol or '',
            'currency_position': self.env.company.currency_id.position or 'after',
        }

    @api.model
    def _get_warehouse_stats(self, warehouse):
        Quant = self.env['stock.quant']
        quant_domain = [
            ('location_id', 'child_of', warehouse.view_location_id.id),
            ('location_id.usage', '=', 'internal'),
        ]
        quant_groups = Quant._read_group(
            quant_domain,
            groupby=['product_id'],
            aggregates=['quantity:sum', 'reserved_quantity:sum'],
        )

        product_ids = [g[0].id for g in quant_groups if g[0]]
        products = self.env['product.product'].browse(product_ids)
        products_ctx = products.with_context(warehouse=warehouse.id)

        units = 0.0
        value = 0.0
        low_stock = 0
        out_of_stock = 0
        for product, qty, reserved in quant_groups:
            if not product:
                continue
            units += qty
            value += qty * product.list_price
            reorder_min = self._get_reorder_min(product, warehouse)
            if qty <= 0:
                out_of_stock += 1
                low_stock += 1
            elif qty <= reorder_min:
                low_stock += 1

        good_stock = max(0, len(products) - low_stock)
        incoming = sum(products_ctx.mapped('incoming_qty'))
        outgoing = sum(products_ctx.mapped('outgoing_qty'))

        return {
            'id': warehouse.id,
            'name': warehouse.name,
            'code': warehouse.code or '',
            'location': (warehouse.partner_id.city if warehouse.partner_id else None) or warehouse.name,
            'active': warehouse.active,
            'products': len(products),
            'units': units,
            'value': value,
            'incoming': incoming,
            'outgoing': outgoing,
            'low_stock': low_stock,
            'out_of_stock': out_of_stock,
            'good_stock': good_stock,
        }

    @api.model
    def _get_reorder_min(self, product, warehouse):
        orderpoint = self.env['stock.warehouse.orderpoint'].search([
            ('product_id', '=', product.id),
            ('warehouse_id', '=', warehouse.id),
        ], limit=1)
        if orderpoint:
            return orderpoint.product_min_qty
        return 5.0

    # ------------------------------------------------------------------
    # Warehouse product table
    # ------------------------------------------------------------------
    @api.model
    def get_warehouse_products(self, warehouse_id=0, search='', category_id=False,
                               status='all', offset=0, limit=20):
        Product = self.env['product.product']
        domain = [('is_storable', '=', True), ('active', '=', True)]
        if search:
            domain += ['|', '|',
                       ('name', 'ilike', search),
                       ('default_code', 'ilike', search),
                       ('barcode', 'ilike', search)]
        if category_id:
            domain += [('categ_id', 'child_of', int(category_id))]

        warehouse = self.env['stock.warehouse'].browse(warehouse_id) if warehouse_id else False
        products = Product.search(domain, order='name')
        if warehouse:
            products = products.with_context(warehouse=warehouse.id)

        quant_domain = [
            ('product_id', 'in', products.ids),
            ('location_id.usage', '=', 'internal'),
        ]
        if warehouse:
            quant_domain.append(('location_id', 'child_of', warehouse.view_location_id.id))

        quant_groups = self.env['stock.quant']._read_group(
            quant_domain,
            groupby=['product_id'],
            aggregates=['quantity:sum', 'reserved_quantity:sum'],
        )
        quant_map = {g[0].id: (g[1], g[2]) for g in quant_groups if g[0]}

        rows = []
        for product in products:
            on_hand, reserved = quant_map.get(product.id, (0.0, 0.0))
            free = on_hand - reserved
            incoming = product.incoming_qty
            outgoing = product.outgoing_qty

            if on_hand <= 0:
                row_status = 'out_of_stock'
            elif warehouse and on_hand <= self._get_reorder_min(product, warehouse):
                row_status = 'low_stock'
            elif on_hand <= 5:
                row_status = 'low_stock'
            else:
                row_status = 'good_stock'

            if status == 'low_stock' and row_status != 'low_stock':
                continue
            if status == 'out_of_stock' and row_status != 'out_of_stock':
                continue
            if status == 'incoming' and incoming <= 0:
                continue
            if status == 'outgoing' and outgoing <= 0:
                continue

            tracking = product.tracking  # 'none' | 'lot' | 'serial'
            rows.append({
                'id': product.id,
                'name': product.display_name,
                'image_url': f'/web/image/product.product/{product.id}/image_128',
                'default_code': product.default_code or '—',
                'category': product.categ_id.complete_name or product.categ_id.name or '—',
                'on_hand': on_hand,
                'free': free,
                'incoming': incoming,
                'outgoing': outgoing,
                'reserved': reserved,
                'value': on_hand * product.list_price,
                'status': row_status,
                'tracking': tracking,
                'is_tracked': tracking in ('lot', 'serial'),
            })

        total = len(rows)
        rows = rows[offset:offset + limit]

        return {
            'warehouse': {
                'id': warehouse.id if warehouse else 0,
                'name': warehouse.name if warehouse else 'All Warehouses',
            },
            'rows': rows,
            'total': total,
            'currency_symbol': self.env.company.currency_id.symbol or '',
        }

    @api.model
    def get_categories(self):
        categories = self.env['product.category'].search([])
        return [{'id': c.id, 'name': c.complete_name or c.name} for c in categories]

    # ------------------------------------------------------------------
    # Serial / lot unit breakdown for a tracked product
    # ------------------------------------------------------------------
    @api.model
    def get_product_units(self, product_id, warehouse_id=0):
        """Return individual quant lines (serial/lot) for a product.

        Mirrors the standard Update Quantity / Internal Locations view:
        Location, Lot/Serial, On Hand, Reserved — plus any common custom
        fields (VIN, shipment ref) when they exist on stock.lot.
        """
        product = self.env['product.product'].browse(int(product_id))
        if not product.exists():
            return {'units': [], 'tracking': 'none', 'product_name': ''}

        quant_domain = [
            ('product_id', '=', product.id),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '!=', 0),
        ]
        if warehouse_id:
            warehouse = self.env['stock.warehouse'].browse(int(warehouse_id))
            if warehouse.exists():
                quant_domain.append(
                    ('location_id', 'child_of', warehouse.view_location_id.id)
                )

        quants = self.env['stock.quant'].search(quant_domain, order='lot_id, location_id')

        # Detect optional custom fields on stock.lot (safe — no crash if missing)
        Lot = self.env['stock.lot']
        lot_fields = Lot._fields
        has_vin = 'x_vin' in lot_fields or 'vin' in lot_fields
        vin_field = 'x_vin' if 'x_vin' in lot_fields else ('vin' if 'vin' in lot_fields else None)
        # shipment-style refs sometimes live on lot.ref or a custom field
        has_ref = 'ref' in lot_fields

        units = []
        for q in quants:
            lot = q.lot_id
            vin = ''
            serial = ''
            shipment = ''
            if lot:
                serial = lot.name or ''
                if vin_field:
                    vin = getattr(lot, vin_field, '') or ''
                if has_ref:
                    shipment = lot.ref or ''
                # Some databases store VIN as the lot name itself
                if not vin and product.tracking == 'serial':
                    vin = serial

            units.append({
                'id': q.id,
                'location': q.location_id.complete_name or q.location_id.name,
                'lot_id': lot.id if lot else False,
                'vin': vin or '—',
                'serial': serial or '—',
                'shipment': shipment or '—',
                'on_hand': q.quantity,
                'reserved': q.reserved_quantity,
                'free': q.quantity - q.reserved_quantity,
            })

        return {
            'product_id': product.id,
            'product_name': product.display_name,
            'tracking': product.tracking,
            'units': units,
        }


    # ------------------------------------------------------------------
    # Products gallery
    # ------------------------------------------------------------------
    @api.model
    def get_products_gallery(self, search='', category_id=False, status='all',
                             favorite_only=False, offset=0, limit=24):
        """Premium product cards for the Inventory > Products gallery."""
        Product = self.env['product.product']
        # Show all Goods (storable or not) so nothing already created is
        # hidden just because "Track Inventory" wasn't checked. Non-tracked
        # items simply show 0 on-hand/reserved/free, which is accurate.
        domain = [('type', '=', 'consu'), ('active', '=', True)]
        if search:
            domain += ['|', '|',
                       ('name', 'ilike', search),
                       ('default_code', 'ilike', search),
                       ('barcode', 'ilike', search)]
        if category_id:
            domain += [('categ_id', 'child_of', int(category_id))]

        products = Product.search(domain, order='name', limit=500)

        quant_groups = self.env['stock.quant']._read_group(
            [
                ('product_id', 'in', products.ids),
                ('location_id.usage', '=', 'internal'),
            ],
            groupby=['product_id'],
            aggregates=['quantity:sum', 'reserved_quantity:sum'],
        )
        quant_map = {g[0].id: (g[1], g[2]) for g in quant_groups if g[0]}

        currency = self.env.company.currency_id
        rows = []
        for product in products:
            on_hand, reserved = quant_map.get(product.id, (0.0, 0.0))
            free = on_hand - reserved
            if on_hand <= 0:
                row_status = 'out_of_stock'
            elif on_hand <= 5:
                row_status = 'low_stock'
            else:
                row_status = 'good_stock'

            tracking = product.tracking or 'none'
            tmpl = product.product_tmpl_id
            # Optional model / favorite fields (safe if missing)
            model_code = ''
            for fname in (
                'product_model', 'x_product_model', 'x_studio_product_model',
                'model', 'x_model',
            ):
                if fname in tmpl._fields:
                    val = tmpl[fname]
                    if val:
                        model_code = val if isinstance(val, str) else str(val)
                        break
            # Odoo 18 standard favorite flag on product.template
            is_favorite = bool(getattr(tmpl, 'is_favorite', False))

            rows.append({
                'id': product.id,
                'tmpl_id': tmpl.id,
                'name': product.name,
                'display_name': product.display_name,
                'default_code': product.default_code or '',
                'model_code': model_code,
                'barcode': product.barcode or '',
                'category': product.categ_id.name or '—',
                'category_id': product.categ_id.id,
                'image_url': f'/web/image/product.product/{product.id}/image_256',
                'list_price': product.list_price,
                'standard_price': product.standard_price,
                'on_hand': on_hand,
                'free': free,
                'reserved': reserved,
                'incoming': product.incoming_qty,
                'outgoing': product.outgoing_qty,
                'status': row_status,
                'tracking': tracking,
                'is_tracked': tracking in ('lot', 'serial'),
                'is_favorite': is_favorite,
                'uom': product.uom_id.name if product.uom_id else '',
                'description': (product.description_sale or product.description or '')[:120],
            })

        if favorite_only:
            rows = [r for r in rows if r.get('is_favorite')]

        counts = {
            'all': len(rows),
            'in_stock': sum(1 for r in rows if r['status'] != 'out_of_stock'),
            'low_stock': sum(1 for r in rows if r['status'] == 'low_stock'),
            'out_of_stock': sum(1 for r in rows if r['status'] == 'out_of_stock'),
        }

        if status == 'low_stock':
            rows = [r for r in rows if r['status'] == 'low_stock']
        elif status == 'out_of_stock':
            rows = [r for r in rows if r['status'] == 'out_of_stock']
        elif status == 'in_stock':
            rows = [r for r in rows if r['status'] != 'out_of_stock']

        total = len(rows)
        page = rows[offset:offset + limit]
        total_on_hand = sum(r['on_hand'] for r in rows)
        total_value = sum(r['on_hand'] * (r['list_price'] or 0) for r in rows)

        return {
            'rows': page,
            'total': total,
            'counts': counts,
            'total_on_hand': total_on_hand,
            'total_value': total_value,
            'currency_symbol': currency.symbol or '',
            'currency_position': currency.position or 'after',
        }

    @api.model
    def toggle_product_favorite(self, tmpl_id):
        """Toggle standard is_favorite on product.template. Returns new state."""
        tmpl = self.env['product.template'].browse(int(tmpl_id))
        if not tmpl.exists():
            return False
        if 'is_favorite' not in tmpl._fields:
            return False
        tmpl.is_favorite = not bool(tmpl.is_favorite)
        return bool(tmpl.is_favorite)
