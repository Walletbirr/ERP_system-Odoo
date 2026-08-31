from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _


class HrPayslipEmployees(models.TransientModel):
    _inherit = "hr.payslip.employees"

    line_ids = fields.One2many(
        "hr.payslip.employees.line",
        "wizard_id",
        string="Employee Details",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        employee_ids = res.get("employee_ids") or self.env.context.get(
            "default_employee_ids"
        )
        if employee_ids and "line_ids" in fields_list:
            emp_ids = []
            if isinstance(employee_ids, list):
                for item in employee_ids:
                    if (
                        isinstance(item, (list, tuple))
                        and len(item) >= 3
                        and item[0] == 6
                    ):
                        emp_ids = item[2]
                    elif isinstance(item, int):
                        emp_ids.append(item)
            else:
                emp_ids = employee_ids
            lines = []
            for emp in self.env["hr.employee"].browse(emp_ids):
                lines.append(
                    (
                        0,
                        0,
                        {
                            "employee_id": emp.id,
                            "not_worked_days": 0.0,
                        },
                    )
                )
            res["line_ids"] = lines
        return res

    @api.onchange("employee_ids")
    def _onchange_employee_ids(self):
        """Sync detail lines with the selected employees.
        Keep any already entered not_worked_days values.
        """
        existing_days = {
            line.employee_id.id: line.not_worked_days
            for line in self.line_ids
            if line.employee_id
        }

        commands = [(5, 0, 0)]  # clear all
        for emp in self.employee_ids:
            commands.append(
                (
                    0,
                    0,
                    {
                        "employee_id": emp.id,
                        "not_worked_days": existing_days.get(emp.id, 0.0),
                    },
                )
            )
        self.line_ids = commands

    def compute_sheet(self):
        self.ensure_one()

        # Keep only lines that actually have an employee
        valid_lines = self.line_ids.filtered(lambda l: l.employee_id)

        if not valid_lines and not self.employee_ids:
            raise UserError(_("You must select employee(s) to generate payslip(s)."))

        # If lines are missing but employees are selected, rebuild them
        if not valid_lines and self.employee_ids:
            self._onchange_employee_ids()
            valid_lines = self.line_ids.filtered(lambda l: l.employee_id)

        if not valid_lines:
            raise UserError(_("You must select employee(s) to generate payslip(s)."))

        payslips = self.env["hr.payslip"]
        active_id = self.env.context.get("active_id")
        if not active_id:
            raise UserError(_("Payslip Run is required."))

        run = self.env["hr.payslip.run"].browse(active_id)
        run_data = run.read(["date_start", "date_end", "credit_note", "struct_id"])[0]
        from_date = run_data.get("date_start")
        to_date = run_data.get("date_end")
        struct_id = run_data.get("struct_id")
        credit_note = run_data.get("credit_note")

        for line in valid_lines:
            employee = line.employee_id
            slip_data = self.env["hr.payslip"].get_payslip_vals(
                from_date,
                to_date,
                employee.id,
                contract_id=False,
                struct_id=struct_id,
            )
            value = slip_data.get("value", {})

            input_lines = [(0, 0, x) for x in value.get("input_line_ids", [])]
            if line.not_worked_days:
                contract_id = value.get("contract_id")
                if not contract_id and employee:
                    contracts = employee._get_contracts(
                        date_from=from_date, date_to=to_date
                    )
                    contract_id = contracts[:1].id if contracts else False

                input_lines.append(
                    (
                        0,
                        0,
                        {
                            "name": _("Not Worked Days"),
                            "code": "UNPAID_DAYS",
                            "amount": line.not_worked_days,
                            "contract_id": contract_id,
                            "sequence": 90,
                        },
                    )
                )

            res = {
                "employee_id": employee.id,
                "name": value.get("name"),
                "struct_id": value.get("struct_id"),
                "contract_id": value.get("contract_id"),
                "payslip_run_id": active_id,
                "input_line_ids": input_lines,
                "worked_days_line_ids": [
                    (0, 0, x) for x in value.get("worked_days_line_ids", [])
                ],
                "date_from": from_date,
                "date_to": to_date,
                "credit_note": credit_note,
                "company_id": employee.company_id.id,
            }
            payslips += self.env["hr.payslip"].create(res)

        payslips._compute_name()
        payslips.compute_sheet()
        return {"type": "ir.actions.act_window_close"}


class HrPayslipEmployeesLine(models.TransientModel):
    _name = "hr.payslip.employees.line"
    _description = "Generate Payslips - Employee Line"

    wizard_id = fields.Many2one(
        "hr.payslip.employees",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    # Not required at DB level so empty phantom lines from the UI
    # do not block the Generate button. We filter them in compute_sheet.
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=False,
    )
    work_phone = fields.Char(
        related="employee_id.work_phone",
        string="Work Phone",
        readonly=True,
    )
    work_email = fields.Char(
        related="employee_id.work_email",
        string="Work Email",
        readonly=True,
    )
    department_id = fields.Many2one(
        related="employee_id.department_id",
        string="Department",
        readonly=True,
    )
    job_id = fields.Many2one(
        related="employee_id.job_id",
        string="Job Position",
        readonly=True,
    )
    parent_id = fields.Many2one(
        related="employee_id.parent_id",
        string="Manager",
        readonly=True,
    )
    monthly_salary = fields.Float(
        string="Monthly Salary",
        compute="_compute_monthly_salary",
        digits="Payroll",
        readonly=True,
    )
    not_worked_days = fields.Float(
        string="Not Worked Days",
        default=0.0,
        help="Number of days the employee did not work. "
        "This value is injected as payslip input UNPAID_DAYS "
        "and can be used by salary rules to deduct salary.",
    )

    @api.depends("employee_id")
    def _compute_monthly_salary(self):
        for line in self:
            wage = 0.0
            if line.employee_id:
                contracts = line.employee_id._get_contracts(
                    date_from=fields.Date.context_today(self),
                    date_to=fields.Date.context_today(self),
                    states=["open", "draft"],
                )
                if contracts:
                    wage = contracts[0].wage or 0.0
                else:
                    contracts = line.employee_id.contract_ids.filtered(
                        lambda c: c.state in ("open", "draft")
                    )
                    if contracts:
                        wage = contracts[0].wage or 0.0
            line.monthly_salary = wage

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        self._compute_monthly_salary()
