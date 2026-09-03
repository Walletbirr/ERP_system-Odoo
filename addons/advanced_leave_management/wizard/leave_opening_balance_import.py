# -*- coding: utf-8 -*-
import base64
import csv
import io

from odoo import fields, models, _
from odoo.exceptions import UserError


class LeaveOpeningBalanceImport(models.TransientModel):
    _name = 'leave.opening.balance.import'
    _description = 'Bulk Opening Balance Import (Migration Tool)'

    leave_type_id = fields.Many2one('leave.type', required=True,
                                     help="All rows in the file are imported against this Leave Type.")
    file = fields.Binary(required=True, string="File (.xlsx or .csv)")
    filename = fields.Char()
    default_effective_date = fields.Date(
        default=fields.Date.context_today,
        help="Used for any row that leaves the Effective Date column blank.")
    default_reason = fields.Char(default="Opening balance migration")
    result_log = fields.Text(readonly=True)

    def _parse_rows(self):
        """Expected columns (header row required, case-insensitive):
        Employee | Balance | Effective Date (optional) | Reason (optional)
        Employee is matched by exact hr.employee name (case-insensitive, trimmed).
        """
        self.ensure_one()
        if not self.file:
            raise UserError(_("Please attach a file."))
        raw = base64.b64decode(self.file)
        name = (self.filename or '').lower()

        rows = []
        if name.endswith('.csv'):
            text = raw.decode('utf-8-sig')
            reader = csv.reader(io.StringIO(text))
            data = list(reader)
        elif name.endswith('.xlsx'):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
            ws = wb.worksheets[0]
            data = [list(r) for r in ws.iter_rows(values_only=True)]
        else:
            raise UserError(_("Unsupported file type. Please upload a .xlsx or .csv file."))

        if not data:
            return rows
        header = [str(h).strip().lower() if h else '' for h in data[0]]
        try:
            idx_emp = header.index('employee')
            idx_bal = header.index('balance')
        except ValueError:
            raise UserError(_(
                "The file must have 'Employee' and 'Balance' columns in the header row. "
                "Optional columns: 'Effective Date', 'Reason'."))
        idx_date = header.index('effective date') if 'effective date' in header else None
        idx_reason = header.index('reason') if 'reason' in header else None

        for row in data[1:]:
            if row is None or not any(row):
                continue
            emp_name = row[idx_emp]
            balance = row[idx_bal]
            if emp_name in (None, '') or balance in (None, ''):
                continue
            eff_date = row[idx_date] if idx_date is not None and idx_date < len(row) else None
            reason = row[idx_reason] if idx_reason is not None and idx_reason < len(row) else None
            rows.append({
                'employee_name': str(emp_name).strip(),
                'balance': float(balance),
                'effective_date': eff_date,
                'reason': reason,
            })
        return rows

    def action_import(self):
        self.ensure_one()
        rows = self._parse_rows()
        Employee = self.env['hr.employee']
        Allocation = self.env['leave.allocation']

        log_lines = []
        success, failed = 0, 0

        for row in rows:
            employee = Employee.search([('name', '=ilike', row['employee_name'])], limit=1)
            if not employee:
                failed += 1
                log_lines.append(_("FAILED - no employee found matching '%s'", row['employee_name']))
                continue
            if len(Employee.search([('name', '=ilike', row['employee_name'])])) > 1:
                log_lines.append(_(
                    "WARNING - multiple employees named '%s', used the first match", row['employee_name']))

            allocation = Allocation.search([
                ('employee_id', '=', employee.id),
                ('leave_type_id', '=', self.leave_type_id.id),
            ], limit=1)
            if not allocation:
                allocation = Allocation.create({
                    'employee_id': employee.id,
                    'leave_type_id': self.leave_type_id.id,
                })

            eff_date = row['effective_date'] or self.default_effective_date
            if hasattr(eff_date, 'date'):
                eff_date = eff_date.date()
            reason = row['reason'] or self.default_reason

            allocation.action_set_opening_balance(row['balance'], eff_date, reason)
            success += 1
            log_lines.append(_(
                "OK - %(emp)s set to %(bal).1f days as of %(date)s",
                emp=employee.name, bal=row['balance'], date=eff_date))

        self.result_log = _("Imported: %(ok)s succeeded, %(fail)s failed.\n\n", ok=success, fail=failed) \
            + "\n".join(log_lines)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'leave.opening.balance.import',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
