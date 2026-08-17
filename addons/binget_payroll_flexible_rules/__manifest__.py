# Part of Binget Holding customizations. See LICENSE file for full copyright and licensing details.
{
    "name": "Payroll Flexible Salary Rules",
    "summary": "Pick which rules of a shared salary structure apply to each payslip",
    "description": """
Adds a "Get Salary Rules" button on the payslip. It loads every rule from the
assigned salary structure (and its parent structures), the same way the
structure form itself lists rules. You can then remove any rule that does not
apply to this particular employee before hitting Compute Sheet - so one
salary structure can be shared by every employee while each payslip only
computes the rules relevant to that person.
""",
    "version": "18.0.1.0.0",
    "category": "Human Resources/Payroll",
    "author": "Binget Holding",
    "license": "AGPL-3",
    "depends": ["payroll"],
    "data": [
        "views/hr_payslip_views.xml",
    ],
    "installable": True,
    "application": False,
}
