# Payroll - Not Worked Days on Generate

Odoo 18 custom module for the OCA Payroll module.

## What it does

Extends the **Generate Payslips** wizard (Payslips Batches → Generate Payslips) with two extra columns:

| Column            | Description                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| **Monthly Salary**| Read-only. Shows the wage of the employee’s current open/draft contract.   |
| **Not Worked Days**| Optional. HR enters the number of days the employee did not work.         |

When the payslip is generated, any value entered in **Not Worked Days** is stored as a Payslip Input with the code:

```
UNPAID_DAYS
```

A sample (inactive) salary rule is provided that deducts:

```
-(contract.wage / 30.0) * UNPAID_DAYS
```

You can change the divisor (30) to match your company policy.

## Installation

1. Copy the folder `payroll_not_worked_days` into your Odoo addons path.
2. Update the Apps list.
3. Install **Payroll - Not Worked Days on Generate**.

## After installation

1. Go to **Payroll → Configuration → Salary Rules**.
2. Find **Not Worked Days Deduction** (it is inactive by default).
3. Review / adjust the Python formula if needed.
4. Set **Active = True**.
5. Add the rule to the salary structure(s) you use (the rule will only compute when the input `UNPAID_DAYS` is present).

## How to use

1. Open a **Payslips Batch**.
2. Click **Generate Payslips**.
3. Add employees (or they may already be listed).
4. Optionally fill **Not Worked Days** for each employee.
5. Click **Generate**.

The payslips are created and computed; the deduction appears only for employees who have a value in Not Worked Days (and only after you activated + linked the salary rule).

## Technical notes

- New transient model: `hr.payslip.employees.line`
- The original Many2many `employee_ids` is kept (hidden) for compatibility.
- The module depends only on `payroll` (OCA).
