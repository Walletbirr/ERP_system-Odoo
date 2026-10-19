# -*- coding: utf-8 -*-
{
    "name": "Stock GRN Document (Internal Transfers)",
    "summary": "Require a scanned GRN document (PDF/image) before validating internal transfers.",
    "description": """
Adds a "GRN Document" file field to stock.picking, shown right below
"Source Document" in the form view — but ONLY for internal transfers
(picking_type_code == 'internal'). Receipts from purchase, deliveries,
manufacturing operations, and every other transfer type are completely
unaffected; the field doesn't even appear for them.

An internal transfer cannot be validated until a GRN document (PDF,
JPG, JPEG, or PNG) is attached. This is enforced twice:
  1. In the view: the field is marked required when it's an internal
     transfer, so the browser blocks the save before it even reaches
     the server.
  2. On the server, inside button_validate(): so the rule can't be
     bypassed via a direct RPC/API call that skips the client-side
     check entirely.

Standalone module — no dependency on theme_shell or custom_login, and
installing/uninstalling it has no effect on either.
""",
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "author": "Binget Holding plc",
    "license": "LGPL-3",
    "depends": ["stock"],
    "data": [
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
