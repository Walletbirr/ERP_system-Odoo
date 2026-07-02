{
    'name': 'Theme Shell - Sidebar Navigation',
    'version': '18.0.1.0.0',
    'summary': 'Replaces the top NavBar app-switcher with a persistent sidebar',
    'category': 'Theme',
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [
            'theme_shell/static/src/sidebar/sidebar.scss',
            'theme_shell/static/src/sidebar/sidebar.js',
            'theme_shell/static/src/sidebar/sidebar.xml',
            'theme_shell/static/src/webclient/webclient_layout.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
