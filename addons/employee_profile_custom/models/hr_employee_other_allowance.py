# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployeeOtherAllowance(models.Model):
    _name = 'hr.employee.other.allowance'
    _description = 'Employee Other Allowance'
    _order = 'date_start desc, id desc'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, ondelete='cascade')
    rule_id = fields.Many2one(
        'hr.salary.rule', string='Other Allowance',
        domain="[('category_id.code', '=', 'OALW')]",
        help="Only salary rules under the Other Allowance (OALW) category "
        "show up here. Selecting one here is what lets this row reach the "
        "employee's contract; a row without one (only possible on data "
        "created before this field existed) falls back to matching by "
        "its text name instead, which is far less reliable.")
    name = fields.Char(string='Other Allowance Name', required=True)
    amount = fields.Monetary(string='Amount', required=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id.id)
    date_start = fields.Date(string='Effective From')
    date_end = fields.Date(string='Effective To')
    active = fields.Boolean(default=True)
    note = fields.Char(string='Note')

    _sql_constraints = [
        ('employee_rule_uniq', 'unique(employee_id, rule_id)',
         'This other allowance is already listed for this employee.'),
    ]

    @api.onchange('rule_id')
    def _onchange_rule_id(self):
        for record in self:
            if record.rule_id:
                record.name = record.rule_id.name

    # ------------------------------------------------------------------
    # Write-through to the contract: same mechanism as
    # hr.employee.allowance (see that model for the full explanation) -
    # an edit here has to reach binget_payroll_compensation's
    # hr.contract.allowance.line, matched by rule_id, with a legacy
    # name-based fallback for rows created before rule_id existed.
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        SalaryRule = self.env['hr.salary.rule']
        for vals in vals_list:
            if vals.get('rule_id') and not vals.get('name'):
                vals['name'] = SalaryRule.browse(vals['rule_id']).name
        records = super().create(vals_list)
        records._push_amount_to_contract()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'amount' in vals or 'rule_id' in vals or 'name' in vals:
            self._push_amount_to_contract()
        return res

    def unlink(self):
        # Deleting this row means "this employee no longer gets this
        # other allowance" - force the matching contract line to 0
        # rather than leaving it holding a stale amount, since payroll
        # never knows this tab exists.
        self._zero_out_contract_lines()
        return super().unlink()

    def _resolve_rule(self, rules_by_key):
        self.ensure_one()
        return self.rule_id or rules_by_key.get((self.name or '').strip().lower())

    def _oalw_rules_by_key(self):
        oalw_rules = self.env['hr.salary.rule'].search(
            [('category_id.code', '=', 'OALW')]
        )
        return {(rule.name or '').strip().lower(): rule for rule in oalw_rules}

    def _push_amount_to_contract(self):
        AllowanceLine = self.env['hr.contract.allowance.line']
        rules_by_key = self._oalw_rules_by_key()
        for record in self:
            employee = record.employee_id
            # Push to every non-cancelled contract, same reasoning as
            # hr.employee.allowance: employee.contract_id only resolves
            # to a Running contract, and a Draft one shouldn't be
            # silently skipped.
            contracts = employee.contract_ids.filtered(
                lambda c: c.state != 'cancel'
            )
            if not contracts:
                continue
            rule = record._resolve_rule(rules_by_key)
            if not rule:
                continue
            for contract in contracts:
                line = contract.allowance_line_ids.filtered(
                    lambda l: l.rule_id == rule
                )
                if line:
                    if line.amount != record.amount:
                        line.amount = record.amount
                else:
                    AllowanceLine.create({
                        'contract_id': contract.id,
                        'rule_id': rule.id,
                        'amount': record.amount,
                    })

    def _zero_out_contract_lines(self):
        rules_by_key = self._oalw_rules_by_key()
        for record in self:
            employee = record.employee_id
            contracts = employee.contract_ids.filtered(
                lambda c: c.state != 'cancel'
            )
            if not contracts:
                continue
            rule = record._resolve_rule(rules_by_key)
            if not rule:
                continue
            for contract in contracts:
                line = contract.allowance_line_ids.filtered(
                    lambda l: l.rule_id == rule
                )
                if line and line.amount:
                    line.amount = 0.0
