{
    'name': 'Friendly Access Denied Message',
    'version': '18.0.1.0.0',
    'summary': 'Replaces the technical Access Error popup with a clean, generic message',
    'description': """
Friendly Access Denied Message
================================
By default, when a user tries to do something outside their permissions,
Odoo shows the technical AccessError message: the internal model name,
the list of security groups that DO have access, etc. This is confusing
for end users and unnecessarily exposes internal security structure to
people who don't have access in the first place.

This module replaces that message everywhere in the system with one
simple, consistent message:

    "You don't have permission to do this. Please contact your
    administrator if you believe this is a mistake."

No other behavior changes - the user still cannot perform the action,
they just see a clean message instead of technical details.
    """,
    'category': 'Tools',
    'author': 'Custom',
    'depends': ['base', 'web'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'access_error_friendly_message/static/src/js/access_denied_dialog.js',
            'access_error_friendly_message/static/src/xml/access_denied_dialog.xml',
        ],
    },
    'assets': {
        'web.assets_backend': [
            'access_error_friendly_message/static/src/js/access_error_dialog_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
