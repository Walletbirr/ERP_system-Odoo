{
    'name': 'Web Offline Page Customization',
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'summary': 'Customize the "You are offline" PWA fallback page (title, message, icon)',
    'description': """
Web Offline Page Customization
===============================

Allows administrators to customize the PWA "You are offline" fallback page
that is shown when the browser loses connection to the Odoo server.

Configurable from Settings > General Settings > Offline Page:
 - Title (replaces "You are offline")
 - Message (replaces the default description text)
 - Icon / logo (replaces the default Odoo icon)
""",
    'author': 'John Nigus',
    'depends': ['web', 'base_setup'],
    'data': [
        'views/webclient_templates.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'web_offline_customize/static/src/js/color_picker_field.js',
            'web_offline_customize/static/src/xml/color_picker_field.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
