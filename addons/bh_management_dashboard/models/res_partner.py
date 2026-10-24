# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    bh_is_staff = fields.Boolean(
        string='Is Staff', index=True, copy=False, tracking=False,
        help="Tick for contacts that are company staff. On the Executive "
             "Dashboard, their outstanding credit is reported under "
             "'From Staff' instead of 'From Customers'. Contacts whose "
             "balance sits on a configured Staff account are counted "
             "automatically, so this is only needed for the others.")
