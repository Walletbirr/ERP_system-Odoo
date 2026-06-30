import os

from lxml import html as lxml_html

import odoo
from odoo import http
from odoo.http import request
from odoo.tools.misc import file_open

from odoo.addons.base.models.ir_qweb import render as qweb_render
from odoo.addons.web.controllers.database import Database as DatabaseController
from odoo.addons.web.controllers.home import Home as HomeController


def _get_global_favicon_url():
    return os.environ.get('WEB_GLOBAL_FAVICON_URL', False)


def _get_brand_name():
    return os.environ.get('WEB_DB_SELECTOR_BRAND_NAME', False)


class Home(HomeController):

    @http.route('/web/login', type='http', auth='none', readonly=False)
    def web_login(self, redirect=None, **kw):
        response = super().web_login(redirect=redirect, **kw)
        if hasattr(response, 'qcontext'):
            favicon_url = _get_global_favicon_url()
            if favicon_url:
                response.qcontext['global_favicon_url'] = favicon_url

            brand_name = _get_brand_name()
            if brand_name:
                response.qcontext['title'] = brand_name
        return response


class Database(DatabaseController):

    def _render_template(self, **d):
        d.setdefault('manage', True)
        d['insecure'] = odoo.tools.config.verify_admin_password('admin')
        d['list_db'] = odoo.tools.config['list_db']
        d['langs'] = odoo.service.db.exp_list_lang()
        d['countries'] = odoo.service.db.exp_list_countries()
        d['pattern'] = '^[a-zA-Z0-9][a-zA-Z0-9_.-]+$'

        try:
            d['databases'] = http.db_list()
            d['incompatible_databases'] = odoo.service.db.list_db_incompatible(d['databases'])
        except odoo.exceptions.AccessDenied:
            d['databases'] = [request.db] if request.db else []

        # Branding, sourced from environment variables since this page is
        # shown before any database is selected (no config_parameter access).
        d['brand_name'] = _get_brand_name() or 'Odoo'
        d['brand_logo_url'] = os.environ.get(
            'WEB_DB_SELECTOR_BRAND_LOGO', '/web/static/img/logo2.png'
        )
        d['global_favicon_url'] = _get_global_favicon_url() or '/web/static/img/favicon.ico'

        templates = {}

        with file_open(
            "web_database_selector_branding/static/src/public/database_manager.qweb.html", "r"
        ) as fd:
            templates['database_manager'] = fd.read()
        with file_open(
            "web/static/src/public/database_manager.master_input.qweb.html", "r"
        ) as fd:
            templates['master_input'] = fd.read()
        with file_open(
            "web/static/src/public/database_manager.create_form.qweb.html", "r"
        ) as fd:
            templates['create_form'] = fd.read()

        def load(template_name):
            fromstring = (
                lxml_html.document_fromstring
                if template_name == 'database_manager'
                else lxml_html.fragment_fromstring
            )
            return (fromstring(templates[template_name]), template_name)

        return qweb_render('database_manager', d, load)
