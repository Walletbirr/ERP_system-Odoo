# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError

# Allowed file types for the scanned GRN paperwork — PDF or a photo of
# the physical document.
GRN_ALLOWED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # "x_" prefix used deliberately, even though this isn't an Odoo
    # Studio-generated field — it's a low-cost way to guarantee this
    # never collides with a field name Odoo core or another module
    # might introduce later.
    x_grn_document = fields.Binary(
        string="GRN Document",
        attachment=True,
        copy=False,
        help="Scanned copy of the paper Goods Receipt Note for this "
        "internal transfer (PDF or image).",
    )
    x_grn_document_filename = fields.Char(
        string="GRN Document Filename",
        copy=False,
    )

    def write(self, vals):
        # Mirrors the view's readonly="state == 'done'" on the server
        # side — the view attribute stops normal editing in the UI, but
        # can't stop a direct write() call (RPC, another module, a
        # script). Only fires when someone is actually trying to change
        # the GRN document itself on an already-done internal transfer;
        # every other field/write is untouched.
        if "x_grn_document" in vals or "x_grn_document_filename" in vals:
            for picking in self:
                if picking.state == "done" and picking.picking_type_code == "internal":
                    raise UserError(
                        _(
                            "The GRN Document for a validated internal "
                            "transfer (%s) can no longer be changed."
                        )
                        % picking.name
                    )
        return super().write(vals)

    def button_validate(self):
        # Deliberately scoped to picking_type_code == "internal" only —
        # this is Odoo's own stable field (related to
        # picking_type_id.code) already used throughout stock's core
        # views to distinguish transfer types, so this check applies to
        # internal transfers alone and never touches receipts,
        # deliveries, manufacturing moves, or any other picking type.
        for picking in self:
            if picking.picking_type_code != "internal":
                continue
            if not picking.x_grn_document:
                raise UserError(
                    _(
                        "Please attach the GRN Document before validating "
                        "this internal transfer (%s)."
                    )
                    % picking.name
                )
            filename = (picking.x_grn_document_filename or "").lower()
            if not filename.endswith(GRN_ALLOWED_EXTENSIONS):
                raise UserError(
                    _(
                        "The GRN Document for %s must be a PDF or an image "
                        "(PDF, JPG, JPEG, or PNG)."
                    )
                    % picking.name
                )
        return super().button_validate()
