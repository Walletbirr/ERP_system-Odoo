from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # NOTE: `is_import` is defined in the shipment_tracking module
    # (models/purchase_order.py), which this module depends on. It's not
    # redefined here - lc_management only adds the LC-specific field and
    # logic on top of that existing "is this an import order" flag.

    lc_id = fields.Many2one(
        'lc.management',
        string="Letter of Credit",
        domain="[('partner_id', '=', partner_id), ('state', 'in', ('open', 'utilized'))]"
    )

    # -------------------------
    # ONCHANGE: IMPORT TOGGLE
    # -------------------------
    @api.onchange('is_import')
    def _onchange_is_import(self):
        # Switching back to "local" clears any LC that was selected while
        # the order was flagged as an import, so it can't linger unseen.
        if not self.is_import:
            self.lc_id = False

    # -------------------------
    # ONCHANGE: LC SELECTION
    # -------------------------
    @api.onchange('lc_id')
    def _onchange_lc_id(self):
        if self.lc_id:
            lc = self.lc_id

            if lc.state not in ('open', 'utilized'):
                raise ValidationError("Only an Open or Utilized LC can be selected.")

            if self.amount_total and self.amount_total > lc.remaining_amount:
                raise ValidationError(
                    f"Selected LC does not have enough balance.\nRemaining: {lc.remaining_amount}"
                )

            self.partner_id = lc.partner_id

    # -------------------------
    # ONCHANGE: VENDOR CHANGE
    # -------------------------
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.lc_id and self.partner_id:
            if self.lc_id.partner_id != self.partner_id:
                raise ValidationError(
                    "Selected LC does not belong to this supplier."
                )

    # -------------------------
    # CONFIRMATION VALIDATION
    # -------------------------
    def button_confirm(self):
        for po in self:
            if not po.is_import:
                # Local purchase: no LC involved, nothing to validate.
                continue

            if not po.lc_id:
                raise ValidationError("Please assign LC before confirming.")

            lc = po.lc_id

            if lc.state not in ('open', 'utilized'):
                raise ValidationError("LC is not active.")

            if po.partner_id != lc.partner_id:
                raise ValidationError(
                    f"LC is issued for {lc.partner_id.name}, "
                    f"but this purchase is for {po.partner_id.name}"
                )

            if po.amount_total > lc.remaining_amount:
                raise ValidationError(
                    f"LC balance exceeded!\nRemaining: {lc.remaining_amount}"
                )

        res = super().button_confirm()

        for po in self:
            if po.is_import and po.lc_id:
                po.lc_id._compute_used_amount()

        return res
