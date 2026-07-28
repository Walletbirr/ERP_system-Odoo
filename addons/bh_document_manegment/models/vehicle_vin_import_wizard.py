import base64
import io
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - openpyxl ships with Odoo
    load_workbook = None


class VehicleVinImportWizard(models.TransientModel):
    _name = 'vehicle.vin.import.wizard'
    _description = 'Import VIN / Serial Numbers onto a Receipt'

    picking_id = fields.Many2one(
        'stock.picking', string='Receipt', required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    import_file = fields.Binary(string='VIN / Serial Excel File', required=True)
    import_filename = fields.Char(string='File Name')

    # Set by action_validate_file(); drives whether the Import button is
    # shown. 'none' = not tested yet, 'valid' = headers OK, 'invalid' =
    # problem found. Never touched by action_import() logic itself.
    x_validation_state = fields.Selection(
        [('none', 'Not Tested'), ('valid', 'Valid'), ('invalid', 'Invalid')],
        default='none', copy=False,
    )
    x_validation_message = fields.Char(copy=False)

    # Recognized header labels (lower-cased) per logical column. "vin" is
    # the current/primary header shown in the UI; the older
    # "Lot/Serial Number Name" variants are still accepted so existing
    # spreadsheets keep working.
    _HEADER_MAP = {
        'product': {'product'},
        'lot_name': {'vin', 'lot/serial number name', 'lot/serial number'},
        'serial': {'serial number'},
        'quantity': {'quantity', 'qty'},
    }

    @api.onchange('import_file')
    def _onchange_import_file(self):
        # A newly picked file has not been tested yet, so any previous
        # pass/fail result no longer applies - hide the Import button
        # again until the person validates the new file.
        self.x_validation_state = 'none'
        self.x_validation_message = False

    def _parse_product(self, text):
        text = (text or '').strip()
        if not text:
            return self.env['product.product']
        Product = self.env['product.product']
        match = re.match(r'^\[(?P<code>[^\]]+)\]\s*(?P<name>.+)$', text)
        if match:
            code = match.group('code').strip()
            product = Product.search([('default_code', '=', code)], limit=1)
            if product:
                return product
            name = match.group('name').strip()
        else:
            name = text
        return (Product.search([('name', '=', name)], limit=1)
                or Product.search([('name', 'ilike', name)], limit=1))

    def _load_workbook_rows(self):
        """Decode the uploaded file and return its raw rows (list of tuples).
        Shared by the validation check and the actual import so both see
        exactly the same data."""
        if load_workbook is None:
            raise UserError(_(
                'openpyxl is not available on this server; the Excel file cannot be read.'
            ))
        content = base64.b64decode(self.import_file)
        try:
            workbook = load_workbook(io.BytesIO(content), data_only=True)
        except Exception:
            raise UserError(_(
                'This file could not be read as an Excel spreadsheet '
                '(.xlsx). Please check the file and try again.'
            ))
        sheet = workbook.worksheets[0]
        raw_rows = list(sheet.iter_rows(values_only=True))
        if not raw_rows:
            raise UserError(_('The uploaded file is empty.'))
        return raw_rows

    def _match_header(self, raw_rows):
        """Match the file's header row (row 1) against _HEADER_MAP.
        Returns (col_idx, missing) where col_idx maps logical column key
        -> spreadsheet column index, and missing lists required logical
        keys ('product', 'lot_name') that were not found."""
        header = [str(cell or '').strip().lower() for cell in raw_rows[0]]
        col_idx = {}
        for key, aliases in self._HEADER_MAP.items():
            for i, cell in enumerate(header):
                if cell in aliases:
                    col_idx[key] = i
                    break
        missing = [k for k in ('product', 'lot_name') if k not in col_idx]
        return col_idx, missing

    def action_validate_file(self):
        """Test the uploaded file's columns against what the import
        expects, without writing anything. Sets x_validation_state /
        x_validation_message so the form can show a pass/fail banner and
        reveal the Import button once the file lines up."""
        self.ensure_one()
        if not self.import_file:
            raise UserError(_('Please upload a file first.'))

        try:
            raw_rows = self._load_workbook_rows()
            col_idx, missing = self._match_header(raw_rows)
        except UserError as exc:
            self.write({
                'x_validation_state': 'invalid',
                'x_validation_message': str(exc),
            })
            return self._reopen_self()

        if missing:
            label_map = {'product': 'Product', 'lot_name': 'VIN'}
            self.write({
                'x_validation_state': 'invalid',
                'x_validation_message': _(
                    'Missing required column(s): %(missing)s. '
                    'Expected headers: Product, VIN, Serial Number, Quantity.'
                ) % {'missing': ', '.join(label_map.get(k, k) for k in missing)},
            })
            return self._reopen_self()

        data_row_count = max(len(raw_rows) - 1, 0)
        found_optional = [
            label for key, label in (('serial', 'Serial Number'), ('quantity', 'Quantity'))
            if key in col_idx
        ]
        message = _(
            'Columns match - Product and VIN found (%(optional)s). '
            '%(rows)s data row(s) ready to import.'
        ) % {
            'optional': (', '.join(found_optional) + ' also found')
                        if found_optional else 'Serial Number / Quantity not present, defaults will be used',
            'rows': data_row_count,
        }
        self.write({
            'x_validation_state': 'valid',
            'x_validation_message': message,
        })
        return self._reopen_self()

    def _reopen_self(self):
        """Re-open this same wizard record in its dialog. Needed because a
        type="object" button that returns no action closes a target="new"
        wizard dialog by default - action_validate_file() must keep the
        dialog open so the person can see the pass/fail banner and then
        click Import."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'bh_document_manegment.view_vehicle_vin_import_wizard_form'
            ).id,
            'target': 'new',
        }

    def _read_rows(self):
        raw_rows = self._load_workbook_rows()
        col_idx, missing = self._match_header(raw_rows)
        if missing:
            raise UserError(_(
                'Could not find required column(s) in the file: %(missing)s\n'
                'Expected headers: Product, VIN, Serial Number, Quantity.'
            ) % {'missing': ', '.join(missing)})

        rows = []
        for raw_row in raw_rows[1:]:
            if raw_row is None or all(v in (None, '') for v in raw_row):
                continue
            lot_name = raw_row[col_idx['lot_name']] if col_idx.get('lot_name') is not None else None
            if not lot_name:
                continue
            serial = raw_row[col_idx['serial']] if 'serial' in col_idx else None
            qty = raw_row[col_idx['quantity']] if 'quantity' in col_idx else 1
            rows.append({
                'product_text': raw_row[col_idx['product']] if col_idx.get('product') is not None else None,
                'lot_name': str(lot_name).strip(),
                'serial': str(serial).strip() if serial not in (None, '') else False,
                'quantity': float(qty) if qty not in (None, '') else 1.0,
            })
        return rows

    def action_import(self):
        self.ensure_one()
        # Safety net: the Import button is only shown once
        # action_validate_file() marks the file valid, but guard here too
        # in case this is ever called another way.
        if self.x_validation_state != 'valid':
            self.action_validate_file()
            if self.x_validation_state != 'valid':
                raise UserError(_(
                    'This file has not passed column validation yet: '
                    '%(msg)s'
                ) % {'msg': self.x_validation_message or _('please test the file first.')})

        rows = self._read_rows()
        if not rows:
            raise UserError(_(
                'No usable rows found in the file (need at least Product '
                'and VIN filled in).'
            ))

        MoveLine = self.env['stock.move.line']
        filled = 0
        created = 0
        issue_rows = []

        for row in rows:
            product = self._parse_product(row['product_text'])
            if not product:
                issue_rows.append(_(
                    'VIN "%(vin)s": product "%(product)s" not found - row skipped'
                ) % {'vin': row['lot_name'], 'product': row['product_text']})
                continue

            # Reuse an existing blank slot on this receipt for this
            # product (no Lot/Serial assigned yet) instead of creating a
            # duplicate line.
            blank_line = MoveLine.search([
                ('picking_id', '=', self.picking_id.id),
                ('product_id', '=', product.id),
                ('lot_id', '=', False),
                ('lot_name', '=', False),
            ], limit=1, order='id asc')

            if blank_line:
                blank_line.write({
                    'lot_name': row['lot_name'],
                    'x_lot_secondary_number': row['serial'],
                    'quantity': row['quantity'],
                })
                filled += 1
                continue

            # No blank slot left. Only create a new line if doing so
            # would not push this product's received quantity past what
            # was actually ordered on this receipt.
            move = self.env['stock.move'].search([
                ('picking_id', '=', self.picking_id.id),
                ('product_id', '=', product.id),
            ], limit=1)
            demand = move.product_uom_qty if move else 0.0
            already_done = sum(MoveLine.search([
                ('picking_id', '=', self.picking_id.id),
                ('product_id', '=', product.id),
            ]).mapped('quantity'))

            if move and already_done + row['quantity'] > demand:
                issue_rows.append(_(
                    'VIN "%(vin)s" (%(product)s): already at ordered quantity '
                    '(%(done)s of %(demand)s) - line not created'
                ) % {
                    'vin': row['lot_name'], 'product': product.display_name,
                    'done': already_done, 'demand': demand,
                })
                continue

            MoveLine.create({
                'picking_id': self.picking_id.id,
                'move_id': move.id if move else False,
                'product_id': product.id,
                'lot_name': row['lot_name'],
                'x_lot_secondary_number': row['serial'],
                'quantity': row['quantity'],
                'location_id': (move.location_id.id if move
                                 else self.picking_id.location_id.id),
                'location_dest_id': (move.location_dest_id.id if move
                                      else self.picking_id.location_dest_id.id),
                'product_uom_id': product.uom_id.id,
            })
            created += 1

        message = _(
            '%(filled)s existing line(s) filled in, %(created)s new line(s) created.'
        ) % {'filled': filled, 'created': created}
        if issue_rows:
            message += '\n\n' + _('Skipped / Issues:') + '\n' + '\n'.join(issue_rows)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('VIN / Serial Import'),
                'message': message,
                'sticky': bool(issue_rows),
                'type': 'warning' if issue_rows else 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }