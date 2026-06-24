from odoo import models, fields, api
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    lc_id = fields.Many2one(
        'lc.management',
        string="Letter of Credit",
        domain="[('partner_id', '=', partner_id), ('state', 'in', ('open', 'utilized'))]"
    )

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
            lc = po.lc_id
            lc._compute_used_amount()

        return res
