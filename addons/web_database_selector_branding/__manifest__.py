{
    'name': 'Database Selector Branding',
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'summary': 'Customize the name and logo on the /web/database/selector and /web/database/manager pages',
    'description': """
Database Selector Branding
============================

Replaces the Odoo name/title and logo shown on the database selector and
database manager pages (the page shown before any database is chosen), and
provides a fallback favicon (via WEB_GLOBAL_FAVICON_URL) for pages where the
web_favicon module's company-based favicon is not available or not set
(e.g. the database selector page, which runs before any company context
exists).

This module depends on web_favicon and builds on top of its existing
web.layout override rather than replacing it, so the two modules do not
conflict. Preference order for the favicon on pages using web.layout
(login page, backend, etc.):

    1. x_icon (set explicitly by some pages, e.g. scoped app install)
    2. the current company's favicon (web_favicon's own logic)
    3. WEB_GLOBAL_FAVICON_URL environment variable (this module)
    4. Odoo's hardcoded default favicon.ico

Because the database selector/manager pages are rendered before any specific
database is selected, their branding is NOT configured from Settings - it is
configured via environment variables:

    WEB_DB_SELECTOR_BRAND_NAME=My Company
    WEB_DB_SELECTOR_BRAND_LOGO=/web_database_selector_branding/static/img/my_logo.png
    WEB_GLOBAL_FAVICON_URL=/web_database_selector_branding/static/img/my_favicon.ico

Set these in your docker-compose.yml (or however you configure environment
variables for the Odoo container), then recreate the container. Replace
static/img/my_logo.png and static/img/my_favicon.ico with your own files
(keep the same filenames, or update the env vars above to point elsewhere).

If the environment variables are not set, the default Odoo branding is used.
""",
    'author': 'Your Company',
    'depends': ['web', 'web_favicon'],
    'data': [
        'views/web_layout_favicon.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
