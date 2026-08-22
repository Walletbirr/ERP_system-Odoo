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
    religion = fields.Char(string='Religion')

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
        """Sync from the given contract's allowance lines. Falls back to
        employee.contract_id (Odoo's "currently running" contract) when no
        contract is passed explicitly - but the caller in hr_contract.py
        always passes the contract that was just created/saved directly,
        since a brand-new contract may still be in Draft and therefore not
        yet reflected in contract_id."""
        Allowance = self.env['hr.employee.allowance']
        for employee in self:
            source = contract if contract is not None else employee.contract_id
            lines = source.allowance_line_ids.filtered('amount') if source else source
            existing_by_rule = {
                a.rule_id: a for a in employee.allowance_ids if a.rule_id
            }
            existing_by_name = {
                a.name: a for a in employee.allowance_ids if not a.rule_id
            }
            for line in lines:
                record = existing_by_rule.get(line.rule_id) or existing_by_name.get(
                    line.rule_id.name
                )
                if record:
                    vals = {}
                    if record.amount != line.amount:
                        vals['amount'] = line.amount
                    if not record.rule_id:
                        # Legacy row from before rule_id existed - link it
                        # up now that we can, instead of leaving it a
                        # name-only guess forever.
                        vals['rule_id'] = line.rule_id.id
                    if vals:
                        record.write(vals)
                else:
                    Allowance.create({
                        'employee_id': employee.id,
                        'rule_id': line.rule_id.id,
                        'name': line.rule_id.name,
                        'amount': line.amount,
                    })

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
