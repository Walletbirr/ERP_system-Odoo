{
    'name': 'Job Position Stunning UI',
    'version': '18.0.1.0.0',
    'summary': 'Modern, card-based redesign of the Job Position form',
    'description': """
Job Position Stunning UI
=========================
Gives the Recruitment > Job Positions form a modern, card-based, animated
visual redesign using custom SCSS and light-touch JS enhancements.

- Gradient header accent + refined spacing
- Card-style grouped fields with icons
- Modern pill-style tabs with auto-added icons
- Toggle-switch style Published / Unpublished radio
- Subtle hover/ripple micro-interactions
- Pure front-end change: no fields, no models, no logic touched
    """,
    'category': 'Human Resources/Recruitment',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['hr_recruitment'],
    'data': [
        'views/hr_job_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hr_job_position_ui/static/src/scss/hr_job_form.scss',
            'hr_job_position_ui/static/src/js/job_form_fx.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
