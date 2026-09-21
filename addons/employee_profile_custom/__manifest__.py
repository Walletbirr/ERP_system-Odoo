{
    'name': 'Employee Profile Custom UI',
    'version': '18.0.3.22.0',
    'category': 'Human Resources',
    'summary': 'Redesigned Employee profile: top tab bar, card-based sections, per-section edit pencil icons',
    'description': """
Employee Profile Custom UI
===========================
Restructures the Employee form (hr.employee) into a clean, top-tabbed,
card-based profile layout inspired by modern HRIS UIs:

- Personal Information
- Guarantee Information
- Educational Background (Education + Certifications combined)
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

Educational Background tab now contains two independent sections
(Education and Certifications) with separate lock controls and
improved modal forms. Education Level, Institution Name, Field of
Study and Degree/Qualification are configurable master data managed
under Employees > Configuration > Educational Background, the same
way core Odoo's Employee Tags are managed - HR can add, rename or
archive options without touching code.

Gender is restricted to Male/Female (the core "Other" option is removed).

Gender, Marital Status, and Blood Type are now configurable master
data too, managed under Employees > Configuration > Personal
Information, the same pattern as Employee Tags - HR can add, rename,
or delete options directly, no code changes needed.
    """,
    'author': 'Custom Development',
    'depends': ['hr', 'hr_contract', 'binget_payroll_compensation', 'binget_employee_benefits', 'binget_attendance'],
    'data': [
        'security/ir.model.access.csv',
        'data/hr_employee_education_config_data.xml',
        'data/hr_employee_profile_config_data.xml',
        'views/hr_contract_views.xml',
        'views/hr_employee_allowance_views.xml',
        'views/hr_employee_other_allowance_views.xml',
        'views/hr_employee_commitment_views.xml',
        'views/hr_employee_education_config_views.xml',
        'views/hr_employee_profile_config_views.xml',
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
