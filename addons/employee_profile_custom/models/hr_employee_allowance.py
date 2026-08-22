# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployeeAllowance(models.Model):
    _name = 'hr.employee.allowance'
    _description = 'Employee Allowance'
    _order = 'date_start desc, id desc'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, ondelete='cascade')
    rule_id = fields.Many2one(
        'hr.salary.rule', string='Allowance',
        domain="[('category_id.code', '=', 'ALW')]",
        help="Only salary rules under the Allowance category show up "
        "here - the same list the Job Position's own Default Allowances "
        "picks from. Selecting one here is what lets this row reach the "
        "employee's contract; a row without one (only possible on data "
        "created before this field existed) falls back to matching by "
        "its text name instead, which is far less reliable.")
    name = fields.Char(string='Allowance Name', required=True)
    allowance_type = fields.Selection([
        ('transport', 'Transport'),
        ('meal', 'Meal'),
        ('housing', 'Housing'),
        ('medical', 'Medical'),
        ('communication', 'Communication'),
        ('other', 'Other'),
    ], string='Type', default='other', required=True)
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
         'This allowance is already listed for this employee.'),
    ]

    @api.onchange('rule_id')
    def _onchange_rule_id(self):
        for record in self:
            if record.rule_id:
                record.name = record.rule_id.name

    # ------------------------------------------------------------------
    # Write-through to the contract: this tab is presented as the place
    # to set/override an employee's allowance amounts, so an edit here
    # has to reach binget_payroll_compensation's hr.contract.allowance.line
    # - that's the only thing get_allowance_amount() ever reads.
    #
    # Matched by rule_id now (a real link, same as hr.job.allowance.line
    # already does) rather than guessing from free text. The name-based
    # match is kept only as a fallback for rows created before this field
    # existed, since those only ever got a text name.
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
        # allowance" - so the matching contract line has to be forced to
        # 0, not just left holding whatever amount it had last. Otherwise
        # payroll would keep quietly paying the old amount forever, since
        # get_allowance_amount() never even knows this tab exists.
        self._zero_out_contract_lines()
        return super().unlink()

    def _resolve_rule(self, rules_by_key):
        self.ensure_one()
        return self.rule_id or rules_by_key.get((self.name or '').strip().lower())

    def _alw_rules_by_key(self):
        alw_rules = self.env['hr.salary.rule'].search(
            [('category_id.code', '=', 'ALW')]
        )
        return {(rule.name or '').strip().lower(): rule for rule in alw_rules}

    def _push_amount_to_contract(self):
        AllowanceLine = self.env['hr.contract.allowance.line']
        rules_by_key = self._alw_rules_by_key()
        for record in self:
            employee = record.employee_id
            # employee.contract_id only resolves to a Running contract -
            # a Draft (or any other non-cancelled) contract was silently
            # skipped here before, leaving it stuck at whatever value it
            # was created with. Push to every non-cancelled contract the
            # employee has instead, so this doesn't depend on state.
            contracts = employee.contract_ids.filtered(
                lambda c: c.state != 'cancel'
            )
            if not contracts:
                # No contract at all yet for this employee - nothing to
                # push onto.
                continue
            rule = record._resolve_rule(rules_by_key)
            if not rule:
                # No Allowance-category salary rule matches this row,
                # even by legacy name-fallback - can't know which
                # contract line to touch.
                continue
            for contract in contracts:
                line = contract.allowance_line_ids.filtered(
                    lambda l: l.rule_id == rule
                )
                if line:
                    # Equality check both avoids a needless write and
                    # stops this from looping forever against
                    # hr_contract.py's own contract -> employee sync
                    # (which is idempotent once amounts already match).
                    if line.amount != record.amount:
                        line.amount = record.amount
                else:
                    AllowanceLine.create({
                        'contract_id': contract.id,
                        'rule_id': rule.id,
                        'amount': record.amount,
                    })

    def _zero_out_contract_lines(self):
        rules_by_key = self._alw_rules_by_key()
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
