import io
import re

from odoo import http
from odoo.http import request

# Technical field -> column header (import-compatible: Odoo matches these labels
# or the technical names when the file is imported again).
PRODUCT_COLUMNS = [
    ('id', 'External ID'),
    ('name', 'Name'),
    ('default_code', 'Internal Reference'),
    ('barcode', 'Barcode'),
    ('categ_id', 'Product Category'),
    ('list_price', 'Sales Price'),
    ('standard_price', 'Cost'),
    ('is_storable', 'Track Inventory'),
]
STOCK_COLUMNS = [
    ('id', 'External ID'),
    ('product_id', 'Product'),
    ('location_id', 'Location'),
    ('inventory_quantity_auto_apply', 'On Hand Quantity'),
]
BOOLEAN_FIELDS = {'is_storable'}


class BingetExport(http.Controller):

    def _xlsx(self, columns, rows, sheet, filename):
        import xlsxwriter  # shipped with Odoo (used by the standard export)

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet(sheet)
        head = wb.add_format({'bold': True, 'bg_color': '#F8F0D8', 'border': 1})
        for c, (_field, label) in enumerate(columns):
            ws.write(0, c, label, head)
            ws.set_column(c, c, max(14, len(label) + 4))
        for r, row in enumerate(rows, start=1):
            for c, ((field, _label), value) in enumerate(zip(columns, row)):
                if field in BOOLEAN_FIELDS:
                    value = 'True' if value else 'False'
                elif value is False or value is None:
                    value = ''
                ws.write(r, c, value)
        ws.freeze_panes(1, 0)
        wb.close()
        return request.make_response(buf.getvalue(), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', f'attachment; filename="{filename}"'),
        ])

    @http.route('/binget/export/products', type='http', auth='user', methods=['POST'])
    def export_products(self, **kw):
        # Same scope as the Products gallery: all active goods.
        products = request.env['product.template'].search(
            [('type', '=', 'consu'), ('active', '=', True)], order='name')
        fields_ = [f for f, _l in PRODUCT_COLUMNS]
        # export_data with 'id' creates/returns the External ID, exactly like
        # the standard "Import-compatible export".
        rows = products.export_data(fields_)['datas']
        return self._xlsx(PRODUCT_COLUMNS, rows, 'Products', 'products.xlsx')

    @http.route('/binget/export/stock', type='http', auth='user', methods=['POST'])
    def export_stock(self, warehouse_id=0, **kw):
        domain = [('location_id.usage', '=', 'internal')]
        name = 'stock.xlsx'
        try:
            warehouse_id = int(warehouse_id or 0)
        except ValueError:
            warehouse_id = 0
        if warehouse_id:
            wh = request.env['stock.warehouse'].browse(warehouse_id).exists()
            if wh:
                domain.append(('location_id', 'child_of', wh.view_location_id.id))
                slug = re.sub(r'[^A-Za-z0-9_-]+', '_', wh.name).strip('_') or 'warehouse'
                name = f'stock_{slug}.xlsx'
        quants = request.env['stock.quant'].search(
            domain, order='product_id, location_id')
        fields_ = [f for f, _l in STOCK_COLUMNS]
        rows = quants.export_data(fields_)['datas']
        return self._xlsx(STOCK_COLUMNS, rows, 'Stock', name)
