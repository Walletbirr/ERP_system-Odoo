# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
    # Kept as a real field (rather than deleted) because other custom
    # modules in this instance may still reference it via view
    # inheritance (xpath expr="//field[@name='religion']"). It's hidden
    # from the Employee Profile UI below - see the view file.
    religion = fields.Char(string='Religion')

    # ------------------------------------------------------------------
    # Gender / Marital Status / Blood Type are now configurable master
    # data (Employees > Configuration), managed the same way as
    # Employee Tags. HR can add, rename, or delete options (e.g. remove
    # "Other") from Configuration with no code changes.
    #
    # The core hr.employee 'gender' / 'marital' Selection fields are
    # kept untouched (still male/female/other and
    # single/married/cohabitant/widower/divorced) and are silently kept
    # in sync from the *_id fields below in create()/write(), purely so
    # any other installed app (payroll rules, reports, etc.) that still
    # reads/writes the native fields keeps working. Blood Type has no
    # such native field, so it's fully replaced.
    # ------------------------------------------------------------------
    gender_id = fields.Many2one('hr.employee.gender', string='Gender')
    marital_status_id = fields.Many2one('hr.employee.marital.status', string='Marital Status')
    blood_type_id = fields.Many2one('hr.employee.blood.type', string='Blood Type')

    # ------------------------------------------------------------------
    # Sync helpers: keep the native gender/marital fields valid so any
    # other module that reads them still gets a sensible value. Custom
    # labels that don't match a native key fall back to 'other' for
    # gender (always a valid choice on the core field) and are simply
    # left untouched for marital status (no safe generic fallback there).
    # ------------------------------------------------------------------
    _GENDER_KEY_MAP = {'male': 'male', 'female': 'female'}
    _MARITAL_KEY_MAP = {
        'single': 'single', 'married': 'married', 'cohabitant': 'cohabitant',
        'widower': 'widower', 'widowed': 'widower', 'divorced': 'divorced',
    }

    def _sync_native_gender_marital(self, vals):
        if 'gender_id' in vals:
            gender_id = vals.get('gender_id')
            if gender_id:
                label = self.env['hr.employee.gender'].browse(gender_id).name or ''
                vals['gender'] = self._GENDER_KEY_MAP.get(label.strip().lower(), 'other')
            else:
                vals['gender'] = False
        if 'marital_status_id' in vals:
            marital_id = vals.get('marital_status_id')
            if marital_id:
                label = self.env['hr.employee.marital.status'].browse(marital_id).name or ''
                key = self._MARITAL_KEY_MAP.get(label.strip().lower())
                if key:
                    vals['marital'] = key
            else:
                vals['marital'] = 'single'
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._sync_native_gender_marital(dict(vals)) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if 'gender_id' in vals or 'marital_status_id' in vals:
            vals = self._sync_native_gender_marital(dict(vals))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Allowance / Commitment / Education / Certification
    # ------------------------------------------------------------------
    allowance_ids = fields.One2many('hr.employee.allowance', 'employee_id', string='Allowances')
    other_allowance_ids = fields.One2many('hr.employee.other.allowance', 'employee_id', string='Other Allowances')
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
    locked_other_allowance = fields.Boolean(string='Other Allowance Locked', default=True)
    locked_benefits = fields.Boolean(string='Benefits Locked', default=True)
    locked_commitment = fields.Boolean(string='Commitment Locked', default=True)

    # ------------------------------------------------------------------
    # Tab stepper - server-side, native-view implementation, no JS.
    #
    # The view no longer uses a real <notebook>/<page> bar. Instead,
    # `profile_step` drives which single content <div> is shown at a
    # time via a plain `invisible="profile_step != '...'"` on each one,
    # and the tab bar itself is a row of plain `type="object"` buttons
    # (two per step - an "active" and a "normal" styled variant, only
    # one of which is ever visible) that all call either
    # action_profile_step_next/_prev or action_profile_step_goto below.
    #
    # Because there is no real browser-native tab widget involved,
    # EVERY navigation - Next, Previous, or clicking any tab label
    # directly, forward or backward, by any amount - is a server round
    # trip that runs through Python validation first. There is nothing
    # purely client-side to bypass. This also means the web client's
    # default behaviour of saving a dirty record before running any
    # `type="object"` button doubles as an auto-save on every one of
    # these clicks.
    #
    # `profile_wizard_active` is a legacy flag from an earlier version
    # where not-yet-reached tabs were hidden entirely; it's no longer
    # read by the view (every tab button is always visible now), but is
    # kept as a harmless breadcrumb of onboarding completion in case
    # it's useful for reporting later.
    # ------------------------------------------------------------------
    _PROFILE_STEP_ORDER = [
        'personal', 'guarantee', 'education', 'experience',
        'contract', 'allowance', 'commitment', 'document',
    ]
    _PROFILE_STEP_REQUIRED_FIELDS = {
        # step key -> [(field_name, human label), ...]
        # Guarantee Information and Contract intentionally have no
        # entries here, so Next passes them through with zero checks.
        'personal': [('name', 'Employee Name')],
        'education': [
            ('education_ids', 'Education'),
        ],
        'experience': [('experience_ids', 'Work Experience')],
        'allowance': [('allowance_ids', 'Allowances')],
        'commitment': [('commitment_ids', 'Commitments')],
    }

    profile_step = fields.Selection(
        [
            ('personal', 'Personal Information'),
            ('guarantee', 'Guarantee Information'),
            ('education', 'Educational Background'),
            ('experience', 'Experience'),
            ('contract', 'Contract'),
            ('allowance', 'Allowance'),
            ('commitment', 'Commitment'),
            ('document', 'Document'),
        ],
        string='Profile Step', default='personal', required=True,
        help="Which profile tab is currently shown. Advances only via "
             "the Next button, once this tab's required fields are "
             "filled in.")

    # Legacy from an earlier version that hid not-yet-reached tabs
    # entirely; no longer read by the view (see the block comment
    # above), kept only as a harmless "has this employee ever finished
    # onboarding" breadcrumb.
    profile_wizard_active = fields.Boolean(
        string='Onboarding In Progress', default=True,
        help="Turned off automatically once the last tab is reached "
             "for the first time.")

    def _profile_step_check_required(self, step):
        """Raise a UserError naming every empty required field for
        `step`, or do nothing if `step` has none configured / all are
        filled in."""
        self.ensure_one()
        missing = []
        for field_name, label in self._PROFILE_STEP_REQUIRED_FIELDS.get(step, []):
            if not self[field_name]:
                missing.append(label)
        if missing:
            raise UserError(_(
                "Please fill in the required field(s) before continuing: %s"
            ) % ", ".join(missing))

    def action_profile_step_next(self):
        self.ensure_one()
        self._profile_step_check_required(self.profile_step)
        order = self._PROFILE_STEP_ORDER
        idx = order.index(self.profile_step)
        if idx + 1 < len(order):
            next_step = order[idx + 1]
            vals = {'profile_step': next_step}
            if idx + 1 == len(order) - 1:
                # Reached the last tab - every step that had a required-
                # field gate has now been satisfied to get here, so treat
                # onboarding as finished and stop hiding tabs from this
                # point on, same as an already-existing employee.
                vals['profile_wizard_active'] = False
            self.write(vals)

    def action_profile_step_prev(self):
        self.ensure_one()
        # Going backward never needs validation.
        order = self._PROFILE_STEP_ORDER
        idx = order.index(self.profile_step)
        if idx - 1 >= 0:
            self.profile_step = order[idx - 1]

    def action_profile_step_goto(self):
        """Jump directly to the tab named in `goto_step` context (used by
        the custom tab-bar buttons in the view). Unlike Next/Previous
        this can skip several steps at once, so every step strictly
        between the current one and the target is validated in order,
        exactly as if Next had been clicked repeatedly to get there.
        Going backward (or to the same tab) is always allowed with no
        checks, same as Previous."""
        self.ensure_one()
        target = self.env.context.get('goto_step')
        order = self._PROFILE_STEP_ORDER
        if not target or target not in order:
            return
        current_idx = order.index(self.profile_step)
        target_idx = order.index(target)
        if target_idx <= current_idx:
            self.profile_step = target
            return
        for step in order[current_idx:target_idx]:
            self._profile_step_check_required(step)
        vals = {'profile_step': target}
        if target_idx == len(order) - 1:
            vals['profile_wizard_active'] = False
        self.write(vals)

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

    def action_unlock_other_allowance(self):
        self.locked_other_allowance = False

    def action_lock_other_allowance(self):
        self.locked_other_allowance = True

    def action_unlock_benefits(self):
        self.locked_benefits = False

    def action_lock_benefits(self):
        self.locked_benefits = True

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
        """Sync the Allowance and Other Allowance tabs from the employee's
        contract.

        Source order:
          1. Explicit contract passed by caller (create/write on hr.contract)
          2. employee.contract_id (Running contract)
          3. Any non-cancelled contract on the employee (covers Draft/import)
          4. If the chosen contract still has no positive allowance lines,
             fall back to the Job Position's Default Allowances so imports
             and contracts created without UI onchanges still populate
             these tabs.

        Lines whose salary rule sits under the Other Allowance (OALW)
        category go to the Other Allowance tab; every other line (ALW
        category, or no category at all - e.g. legacy data) keeps going
        to the regular Allowance tab, exactly as before.
        """
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

            oalw_lines = lines.filtered(lambda l: l.rule_id.category_id.code == 'OALW')
            regular_lines = lines - oalw_lines

            employee._sync_allowance_lines(
                regular_lines, 'hr.employee.allowance', employee.allowance_ids)
            employee._sync_allowance_lines(
                oalw_lines, 'hr.employee.other.allowance', employee.other_allowance_ids)

    def _sync_allowance_lines(self, lines, model_name, existing_records):
        """Shared create/update logic used by both the Allowance and the
        Other Allowance tabs to mirror a set of hr.contract.allowance.line
        records onto their own tab's model."""
        self.ensure_one()
        if not lines:
            return
        Model = self.env[model_name]
        existing_by_rule = {
            r.rule_id: r for r in existing_records if r.rule_id
        }
        existing_by_name = {
            r.name: r for r in existing_records if not r.rule_id
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
                Model.create({
                    'employee_id': self.id,
                    'rule_id': rule.id,
                    'name': rule.name,
                    'amount': amount,
                })

    def action_refresh_allowances_from_contract(self):
        """Manual / bulk refresh of the Allowance and Other Allowance tabs
        from the active contract (or its Job Position defaults). Useful
        after an import that created contracts before this sync logic
        existed."""
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
