from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ShipmentCost(models.Model):
    """
    Restricts Shipment Cost's 'Fee Account' to the Fee Account configured on
    the Letter of Credit linked to the shipment's Purchase Order.

    Chain:  shipment.cost -> shipment_id -> purchase_order_id -> lc_id -> opening_fee_account_id

    If the shipment has no PO, the PO has no LC, or the LC has no Fee Account
    set, 'lc_fee_account_id' is empty and the Fee Account dropdown on
    Shipment Cost will show no records (by design, since an LC-linked PO is
    mandatory for both modules).
    """
    _inherit = 'shipment.cost'

    lc_fee_account_id = fields.Many2one(
        'account.account',
        string='LC Fee Account',
        compute='_compute_lc_fee_account_id',
        store=False,
        help="Fee Account defined on the Letter of Credit linked to this "
             "shipment's Purchase Order. Restricts and auto-fills the "
             "Fee Account field below.",
    )

    @api.depends(
        'shipment_id.purchase_order_id.lc_id.opening_fee_account_id',
    )
    def _compute_lc_fee_account_id(self):
        for rec in self:
            po = rec.shipment_id.purchase_order_id
            lc = po.lc_id if po else False
            rec.lc_fee_account_id = (
                lc.opening_fee_account_id.id
                if lc and lc.opening_fee_account_id else False
            )

    @api.onchange('shipment_id')
    def _onchange_shipment_id_lc_fee_account(self):
        """Auto-fill Fee Account from the linked LC when the Shipment changes."""
        for rec in self:
            rec.fee_account_id = rec.lc_fee_account_id or False

    @api.constrains('fee_account_id', 'shipment_id')
    def _check_fee_account_matches_lc(self):
        """
        Server-side guard so the LC-based restriction can't be bypassed by
        writing fee_account_id directly (e.g. via import, XML-RPC, or a
        stale form).
        """
        for rec in self:
            if not rec.shipment_id or not rec.fee_account_id:
                continue
            po = rec.shipment_id.purchase_order_id
            lc = po.lc_id if po else False
            if lc and lc.opening_fee_account_id and rec.fee_account_id != lc.opening_fee_account_id:
                raise ValidationError(
                    "Fee Account on '%s' must be the Fee Account defined on "
                    "Letter of Credit '%s' (%s)." % (
                        rec.display_name,
                        lc.name,
                        lc.opening_fee_account_id.display_name,
                    )
                )
