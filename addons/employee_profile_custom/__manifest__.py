{
    'name': 'Employee Profile Custom UI',
    'version': '18.0.3.10.0',
    'category': 'Human Resources',
    'summary': 'Redesigned Employee profile: top tab bar, card-based sections, per-section edit pencil icons',
    'description': """
Employee Profile Custom UI
===========================
Restructures the Employee form (hr.employee) into a clean, top-tabbed,
card-based profile layout inspired by modern HRIS UIs:

- Personal Information
- Guarantee Information
- Education Background (Education + Certifications combined)
- Experience
- Contract
- Allowance
- Commitment
- Document

Tabs sit right below the header (photo/name), like a normal profile page,
instead of buried under a long block of fields. Every tab opens READ-ONLY
by default. Each section has a pencil (edit) icon that unlocks just that
section for editing, and a check (done) icon to lock it back after saving.
Contract details open the real Contract record in a dialog so all native
contract logic (Enterprise/Community) keeps working untouched.

Education Background tab now contains two independent sections
(Education and Certifications) with separate lock controls and
improved modal forms.
    """,
    'author': 'Custom Development',
    'depends': ['hr', 'hr_contract', 'binget_payroll_compensation'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_contract_views.xml',
        'views/hr_employee_allowance_views.xml',
        'views/hr_employee_commitment_views.xml',
        'views/hr_employee_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'employee_profile_custom/static/src/css/employee_profile.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
