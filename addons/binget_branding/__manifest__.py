{
    'name': 'Binget Branding',
    'version': '18.0.1.0.0',
    'summary': 'Custom brand colors for header, buttons, and UI',
    'author': 'Custom',
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [ 
            'binget_branding/static/src/scss/brand_colors.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
