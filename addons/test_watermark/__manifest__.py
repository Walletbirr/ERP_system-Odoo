{
    'name': 'Test / UAT Watermark',
    'version': '18.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Adds a configurable watermark overlay to visually flag non-production environments (UAT/Test).',
    'description': """
Test / UAT Watermark
=====================

Adds a repeating, semi-transparent "TEST" (or any custom text) watermark
across the entire system - backend screens, dialogs, and website/portal
pages - so it's always visually obvious you are in a non-production
environment.

Features
--------
* Repeating diagonal watermark text, applied via CSS - does not block clicks.
* Text, color and opacity are configurable from Settings > General Settings.
* Enable/disable without any code change or restart.
* Recommended usage: install ONLY on your UAT/Test database. Do not install
  on Production.

    """,
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'data/ir_config_parameter.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'test_watermark/static/src/js/watermark.js',
        ],
        'web.assets_frontend': [
            'test_watermark/static/src/js/watermark.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
