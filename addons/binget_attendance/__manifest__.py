{
    'name': 'Employee Attendance (Days Absent)',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'HR-managed monthly absence tracking, feeding payroll deductions',
    'description': """
Employee Attendance (Days Absent)
===================================
Lets HR record, per employee per month, how many days that employee was
absent. No self check-in/check-out - entries are made by HR on behalf of
each employee.

- One record per employee per month (Month + auto Year, year is hidden)
- Simple numeric "Days Absent" field, no daily grid
- No approval workflow: HR enters the number and it's saved
- Validation: days absent can't be negative or exceed the number of
  calendar days in the selected month
- Menu lives under Employees, next to Org Chart / Contracts
- Visible only to the HR Officer / HR Manager groups

This module only stores the data. Connecting it to payroll (feeding the
number into a salary rule as an absence deduction) is a separate step,
done directly in the payroll rules once this is reviewed and installed.
    """,
    'author': 'Custom Development',
    'depends': ['hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_attendance_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
