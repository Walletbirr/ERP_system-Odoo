# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ------------------------------------------------------------------
    # Guarantee (Guarantor) Information
    # ------------------------------------------------------------------
    guarantor_name = fields.Char(string='Guarantor Full Name')
    guarantor_phone = fields.Char(string='Guarantor Phone No')
    guarantor_job = fields.Char(string='Guarantor Job')
    guarantor_address = fields.Char(string='Guarantor Address')
    guarantor_salary = fields.Monetary(string='Guarantor Salary', currency_field='currency_id')
    guarantor_id_document = fields.Binary(string='Guarantee ID')
    guarantor_id_document_filename = fields.Char(string='Guarantee ID Filename')
    guarantor_document = fields.Binary(string='Guarantee Document')
    guarantor_document_filename = fields.Char(string='Guarantee Document Filename')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id.id)

    # ------------------------------------------------------------------
    # Extra Personal Information
    # ------------------------------------------------------------------
    blood_type = fields.Selection([
        ('a', 'A'), ('b', 'B'), ('ab', 'AB'), ('o', 'O'),
    ], string='Blood Type')
    # Kept as a real field (rather than deleted) because other custom
    # modules in this instance may still reference it via view
    # inheritance (xpath expr="//field[@name='religion']"). It's hidden
    # from the Employee Profile UI below - see the view file.
    religion = fields.Char(string='Religion')

    # ------------------------------------------------------------------
    # Restrict Gender to Male / Female only (drop the core "Other"
    # option). Overriding the field's selection directly here is
    # simpler and more reliable than trying to hide the choice at the
    # view/widget level, and it applies everywhere gender is used, not
    # just on this profile form.
    # ------------------------------------------------------------------
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
    ], string='Gender')

    # ------------------------------------------------------------------
    # Allowance / Commitment / Education / Certification
    # ------------------------------------------------------------------
    allowance_ids = fields.One2many('hr.employee.allowance', 'employee_id', string='Allowances')
    commitment_ids = fields.One2many('hr.employee.commitment', 'employee_id', string='Commitments')
    education_ids = fields.One2many('hr.employee.education', 'employee_id', string='Education')
    certification_ids = fields.One2many('hr.employee.certification', 'employee_id', string='Certifications')
    experience_ids = fields.One2many('hr.employee.experience', 'employee_id', string='Work Experience')

    # ------------------------------------------------------------------
    # Documents (simple attachment shelf, independent of the chatter)
    # ------------------------------------------------------------------
    profile_document_ids = fields.Many2many(
        'ir.attachment', 'hr_employee_profile_document_rel',
        'employee_id', 'attachment_id', string='Documents')

    # ------------------------------------------------------------------
    # Section lock flags -> drive the read-only / pencil-to-edit UI.
    # Default True (locked/read-only). Pencil button = unlock, check button = lock.
    # ------------------------------------------------------------------
    locked_personal = fields.Boolean(string='Personal Info Locked', default=True)
    locked_guarantor = fields.Boolean(string='Guarantee Info Locked', default=True)
    locked_education = fields.Boolean(string='Education Locked', default=True)
    locked_experience = fields.Boolean(string='Experience Locked', default=True)
    locked_certification = fields.Boolean(string='Certification Locked', default=True)
    locked_allowance = fields.Boolean(string='Allowance Locked', default=True)
    locked_commitment = fields.Boolean(string='Commitment Locked', default=True)

    # ------------------------------------------------------------------
    # Unlock / Lock actions - one pair per tab
    # ------------------------------------------------------------------
    def action_unlock_personal(self):
        self.locked_personal = False

    def action_lock_personal(self):
        self.locked_personal = True

    def action_unlock_guarantor(self):
        self.locked_guarantor = False

    def action_lock_guarantor(self):
        self.locked_guarantor = True

    def action_unlock_education(self):
        self.locked_education = False

    def action_lock_education(self):
        self.locked_education = True

    def action_unlock_experience(self):
        self.locked_experience = False

    def action_lock_experience(self):
        self.locked_experience = True

    def action_unlock_certification(self):
        self.locked_certification = False

    def action_lock_certification(self):
        self.locked_certification = True

    def action_unlock_allowance(self):
        self.locked_allowance = False

    def action_lock_allowance(self):
        self.locked_allowance = True

    def action_unlock_commitment(self):
        self.locked_commitment = False

    def action_lock_commitment(self):
        self.locked_commitment = True

    # ------------------------------------------------------------------
    # Allowance tab: kept in sync with the employee's contract, which is
    # the actual source of truth for what an employee is paid (see
    # binget_payroll_compensation's hr.contract.allowance.line). Called
    # from hr.contract's create()/write() whenever a contract's allowance
    # lines change, so this tab always reflects what's really on the
    # contract instead of being filled in by hand a second time.
    # ------------------------------------------------------------------
    def _sync_allowances_from_contract(self, contract=None):
        """Sync the Allowance tab from the employee's contract.

        Source order:
          1. Explicit contract passed by caller (create/write on hr.contract)
          2. employee.contract_id (Running contract)
          3. Any non-cancelled contract on the employee (covers Draft/import)
          4. If the chosen contract still has no positive allowance lines,
             fall back to the Job Position's Default Allowances so imports
             and contracts created without UI onchanges still populate this tab.
        """
        Allowance = self.env['hr.employee.allowance']
        for employee in self:
            source = contract if contract is not None else employee.contract_id
            if not source:
                candidates = employee.contract_ids.filtered(
                    lambda c: c.state != 'cancel'
                )
                source = candidates.sorted(
                    key=lambda c: (c.date_start or fields.Date.today(), c.id),
                    reverse=True,
                )[:1]

            lines = source.allowance_line_ids.filtered('amount') if source else self.env['hr.contract.allowance.line']

            # Fallback: job defaults when contract lines are empty (import path)
            if not lines and source and source.job_id and source.job_id.allowance_line_ids:
                lines = source.job_id.allowance_line_ids.filtered('amount')

            if not lines:
                continue

            existing_by_rule = {
                a.rule_id: a for a in employee.allowance_ids if a.rule_id
            }
            existing_by_name = {
                a.name: a for a in employee.allowance_ids if not a.rule_id
            }
            for line in lines:
                rule = getattr(line, 'rule_id', False)
                if not rule:
                    continue
                amount = line.amount
                record = existing_by_rule.get(rule) or existing_by_name.get(rule.name)
                if record:
                    vals = {}
                    if record.amount != amount:
                        vals['amount'] = amount
                    if not record.rule_id:
                        vals['rule_id'] = rule.id
                    if vals:
                        record.write(vals)
                else:
                    Allowance.create({
                        'employee_id': employee.id,
                        'rule_id': rule.id,
                        'name': rule.name,
                        'amount': amount,
                    })

    def action_refresh_allowances_from_contract(self):
        """Manual / bulk refresh of the Allowance tab from the active
        contract (or its Job Position defaults). Useful after an import
        that created contracts before this sync logic existed."""
        for employee in self:
            employee._sync_allowances_from_contract()
        return True

    # ------------------------------------------------------------------
    # Contract tab: open the real hr.contract record in a dialog so all
    # native contract logic (accounting, salary rules, etc.) stays intact.
    # ------------------------------------------------------------------
    def action_open_contract(self):
        """Open the employee's actual current contract - Draft included -
        instead of falling back to a blank New Contract dialog just
        because employee.contract_id only ever resolves to a Running
        contract and this one hasn't been set Running yet."""
        self.ensure_one()
        contract = self.contract_id
        if not contract:
            candidates = self.contract_ids.filtered(lambda c: c.state != 'cancel')
            contract = candidates.sorted(
                key=lambda c: (c.date_start or fields.Date.today(), c.id),
                reverse=True,
            )[:1]
        if not contract:
            return self._action_new_contract_dialog()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Contract',
            'res_model': 'hr.contract',
            'view_mode': 'form',
            'res_id': contract.id,
            'target': 'new',
        }

    def action_new_contract(self):
        """Explicit 'create a new contract' entry point, separate from
        action_open_contract (which now opens the existing one whenever
        there is one). Use this when the employee genuinely needs a
        second/replacement contract, not as a fallback for one we
        merely failed to find."""
        self.ensure_one()
        return self._action_new_contract_dialog()

    def _action_new_contract_dialog(self):
        # Pre-fill from the employee's current Work info so the New
        # Contract dialog isn't blank: job_id and department_id are
        # plain fields on hr.contract (not related to hr.employee),
        # so without this they stay empty even though the employee
        # already has them set. Passing job_id here also re-triggers
        # the onchange that fills the Wage and Allowances from the
        # Job Position's defaults. Job Position/Department are
        # unconditionally read-only on the Contract form itself (see
        # hr_contract_view_form_profile_extra), so no context flag is
        # needed here to lock them just for this dialog.
        #
        # default_state='open' means a contract created from this
        # dialog saves straight into Running, rather than sitting in
        # Draft until someone remembers to flip it - which is exactly
        # what was silently breaking the Allowance-tab/contract link.
        default_vals = {
            'default_employee_id': self.id,
            'default_state': 'open',
        }
        if self.job_id:
            default_vals['default_job_id'] = self.job_id.id
        if self.department_id:
            default_vals['default_department_id'] = self.department_id.id
        if self.company_id:
            default_vals['default_company_id'] = self.company_id.id
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Contract',
            'res_model': 'hr.contract',
            'view_mode': 'form',
            'target': 'new',
            'context': default_vals,
        }
