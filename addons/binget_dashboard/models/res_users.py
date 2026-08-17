# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    dashboard_role_ids = fields.Many2many(
        "binget.dashboard.role",
        "binget_dashboard_role_user_rel",
        "user_id",
        "role_id",
        string="Dashboard Role(s)",
        help="Controls what the Binget Dashboard shows this user — set "
             "deliberately by an admin here, independent of this "
             "person's actual Odoo access rights below. A user can "
             "hold several roles at once.",
    )
    dashboard_seen_notifications = fields.Text(
        default="{}",
        help="Internal bookkeeping for the Binget Dashboard: JSON map of "
             "notification id -> the title text this user last acknowledged. "
             "Deliberately NOT used to hide the notification badge count "
             "(that always reflects real unresolved issues) — only to mark "
             "individual items as 'already seen' in the notification panel.",
    )
