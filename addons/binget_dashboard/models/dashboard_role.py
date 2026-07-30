# -*- coding: utf-8 -*-
from odoo import fields, models


class BingetDashboardRole(models.Model):
    """A named, admin-configurable dashboard role — e.g. "Purchase
    Officer", "Warehouse Supervisor" — deliberately separate from
    Odoo's own security groups.

    WHY THIS EXISTS: Odoo's res.groups answer "what can this account
    technically read or write" (access control). They were never
    designed to answer "what is this person's job", and in practice
    the two drift apart — e.g. Purchase staff are commonly given the
    basic Invoicing group just so they can post a vendor bill, which
    technically grants read access to accounting data without making
    them a Finance stakeholder. Inferring the dashboard's content from
    those groups inherits that ambiguity.

    This model breaks that coupling: an admin explicitly decides which
    dashboard section(s) a role unlocks, independent of whatever raw
    CRUD permissions that same person needs for their actual job. The
    dashboard only ever reads this field — never res.groups — to
    decide what to show someone.

    Several named roles can point at the same section (e.g. both
    "Purchase Officer" and "Procurement Lead" could map to code=
    'purchase'), so admins can label things however makes sense for
    the business while the dashboard logic stays anchored to the fixed
    small set of sections it actually knows how to render.
    """
    _name = "binget.dashboard.role"
    _description = "Binget Dashboard Role"
    _order = "sequence, name"

    name = fields.Char(
        required=True,
        help="Label shown here and on the Users form, e.g. 'Purchase Officer'.",
    )
    code = fields.Selection(
        [
            ("admin", "Full Access (Admin)"),
            ("sales", "Sales"),
            ("purchase", "Purchase"),
            ("inventory", "Inventory"),
            ("accounting", "Finance"),
            ("hr", "Workforce"),
            ("manufacturing", "Manufacturing"),
        ],
        required=True,
        help="Which dashboard section this role unlocks. Multiple named "
             "roles can map to the same section.",
    )
    sequence = fields.Integer(default=10)
    description = fields.Char(help="Optional note for other admins, e.g. what this role is meant for.")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "A dashboard role with this name already exists."),
    ]
