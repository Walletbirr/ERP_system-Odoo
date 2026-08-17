# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

RAW_CODE_KEYWORDS = ['account id', 'account code', 'code']
RAW_DESC_KEYWORDS = ['description', 'name', 'label']
RAW_DEBIT_KEYWORDS = ['debit']
RAW_CREDIT_KEYWORDS = ['credit']
# If the uploaded file already contains these, it's the full structured
# format, not a raw export - leave it alone.
STRUCTURED_MARKERS = ['journal', 'reference']


class BingetGlImport(models.TransientModel):
    _inherit = 'base_import.import'

    # ------------------------------------------------------------------
    # detection / column matching helpers
    # ------------------------------------------------------------------
    def _gl_find_col(self, headers_lower, keywords):
        for i, h in enumerate(headers_lower):
            if any(k in h for k in keywords):
                return i
        return None

    def _gl_is_raw_format(self, headers_lower):
        if any(marker in h for h in headers_lower for marker in STRUCTURED_MARKERS):
            return False
        has_debit = any('debit' in h for h in headers_lower)
        has_credit = any('credit' in h for h in headers_lower)
        has_account = any(k in h for h in headers_lower for k in RAW_CODE_KEYWORDS)
        return has_debit and has_credit and has_account

    def _gl_default_journal(self):
        journal = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
        if not journal:
            raise UserError(_(
                "No 'Miscellaneous Operations' type journal was found to post this import "
                "to. Create one in Accounting > Configuration > Journals first."
            ))
        return journal

    # ------------------------------------------------------------------
    # transformation
    # ------------------------------------------------------------------
    def _gl_transform_rows(self, headers, data_rows):
        headers_lower = [str(h or '').strip().lower() for h in headers]
        code_col = self._gl_find_col(headers_lower, RAW_CODE_KEYWORDS)
        desc_col = self._gl_find_col(headers_lower, RAW_DESC_KEYWORDS)
        debit_col = self._gl_find_col(headers_lower, RAW_DEBIT_KEYWORDS)
        credit_col = self._gl_find_col(headers_lower, RAW_CREDIT_KEYWORDS)
        code_col = 0 if code_col is None else code_col
        desc_col = 1 if desc_col is None else desc_col
        debit_col = 2 if debit_col is None else debit_col
        credit_col = 3 if credit_col is None else credit_col

        Account = self.env['account.account']
        clean_rows = []
        missing = []
        debit_total = 0.0
        credit_total = 0.0

        for row in data_rows:
            if code_col >= len(row):
                continue
            code = (row[code_col] or '').strip()
            if not code:
                continue
            desc = row[desc_col].strip() if desc_col < len(row) and row[desc_col] else ''
            if desc.lower() == 'total:':
                continue

            debit_raw = row[debit_col] if debit_col < len(row) else ''
            credit_raw = row[credit_col] if credit_col < len(row) else ''

            account = Account.search([('code', '=', code)], limit=1)
            if not account:
                missing.append('%s (%s)' % (code, desc))
                continue

            try:
                debit_val = float(debit_raw) if debit_raw not in ('', None) else 0.0
            except ValueError:
                debit_val = 0.0
            try:
                credit_val = float(credit_raw) if credit_raw not in ('', None) else 0.0
            except ValueError:
                credit_val = 0.0

            debit_total += debit_val
            credit_total += credit_val

            clean_rows.append({
                'account': '%s %s' % (account.code, account.name),
                'label': desc,
                'debit': debit_raw if debit_raw not in ('', None) else '',
                'credit': credit_raw if credit_raw not in ('', None) else '',
            })

        if missing:
            raise UserError(_(
                "Import stopped - these account codes don't exist in the Chart of Accounts. "
                "Create them first, then re-import:\n\n%s"
            ) % '\n'.join(missing))

        if round(debit_total - credit_total, 2) != 0:
            raise UserError(_(
                "Import stopped - the entry doesn't balance. "
                "Debit total %(debit)s does not equal Credit total %(credit)s."
            ) % {'debit': debit_total, 'credit': credit_total})

        if not clean_rows:
            raise UserError(_("No valid data rows were found in the file."))

        journal = self._gl_default_journal()
        entry_date = fields.Date.context_today(self)

        if self.env.context.get('gl_real_run'):
            reference = self.env['ir.sequence'].sudo().next_by_code('binget.gl.import.ref') or 'JE-0001'
        else:
            reference = 'JE-#### (assigned when you click Import)'

        new_headers = ['Journal', 'Date', 'Reference', 'Account', 'Label', 'Debit', 'Credit']
        new_rows = [new_headers]
        for i, r in enumerate(clean_rows):
            if i == 0:
                new_rows.append([journal.name, str(entry_date), reference,
                                  r['account'], r['label'], r['debit'], r['credit']])
            else:
                new_rows.append(['', '', '', r['account'], r['label'], r['debit'], r['credit']])
        return new_rows

    # ------------------------------------------------------------------
    # hook points
    # ------------------------------------------------------------------
    def _read_file(self, options):
        file_length, rows = super()._read_file(options)
        if self.res_model != 'account.move' or not rows or not options.get('has_headers'):
            return file_length, rows

        headers_lower = [str(h or '').strip().lower() for h in rows[0]]
        if not self._gl_is_raw_format(headers_lower):
            return file_length, rows

        new_rows = self._gl_transform_rows(rows[0], rows[1:])
        return len(new_rows), new_rows

    def execute_import(self, fields, columns, options, dryrun=False):
        # Only the real (non-dryrun) run should consume the reference
        # sequence, so Test / preview calls don't burn numbers. Odoo model
        # objects don't support arbitrary instance attributes (__slots__),
        # so this flag is passed through the environment context instead,
        # which stays attached to `self` for the rest of this call chain.
        return super(BingetGlImport, self.with_context(gl_real_run=not dryrun)).execute_import(
            fields, columns, options, dryrun=dryrun
        )
