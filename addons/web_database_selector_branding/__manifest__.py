{
    'name': 'Database Selector Branding',
    'version': '18.0.1.0.0',
    'category': 'Technical',
    'summary': 'Customize the name and logo on the /web/database/selector and /web/database/manager pages',
    'description': """
Database Selector Branding
============================

Replaces the Odoo name/title and logo shown on the database selector and
database manager pages (the page shown before any database is chosen).

Because this page is rendered before any specific database is selected,
branding is NOT configured from Settings - it is configured via environment
variables, since these are the only thing available at that point that is
not tied to a specific database:

    WEB_DB_SELECTOR_BRAND_NAME=BINGET HOLDING PLC
    WEB_DB_SELECTOR_BRAND_LOGO=/web_database_selector_branding/static/img/my_logo.png

Set these in your docker-compose.yml (or however you configure environment
variables for the Odoo container), then restart the container. Replace
static/img/my_logo.png with your own logo file (keep the same filename, or
update WEB_DB_SELECTOR_BRAND_LOGO to point at your own static path/URL).

If the environment variables are not set, the default Odoo branding is used.
""",
    'author': 'john king',
    'depends': ['web'],
    'data': [],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
