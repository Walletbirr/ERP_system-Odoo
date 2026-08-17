# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BingetDashboardActivityDeletion(models.Model):
    """A small standing record of 'this document was deleted', because
    Odoo's chatter (mail.message / mail.tracking.value) has nothing to
    say about a record once it's gone — there's no row left to attach
    a message to. Populated exclusively by the unlink() overrides below,
    never created directly by a user, and read back only from
    binget.dashboard's _build_activity_rows() (always via sudo()), so
    the ir.model.access entry for regular users is read-only-never
    (see security/ir.model.access.csv) — nobody needs direct model
    access, it's plumbing for the Activity Log/Recent Activity tabs.

    Deliberately denormalized (label/partner/amount copied out at
    delete time as plain text/numbers) rather than any kind of
    reference field, since the whole point is surviving the source
    record's deletion.
    """
    _name = "binget.dashboard.activity.deletion"
    _description = "Binget Dashboard — Deletion Log"
    _order = "delete_date desc"

    res_model = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True)
    type_key = fields.Char(required=True, help="Same type_key vocabulary as _ACTIVITY_TRACKED_MODELS, e.g. 'sale_order', 'invoice', 'contact'.")
    type_label = fields.Char(required=True, help="Human label captured at delete time, e.g. 'Sales Order' — can't be re-derived once the record is gone.")
    label = fields.Char(help="The deleted record's name/reference, e.g. 'S00004'.")
    partner = fields.Char()
    amount = fields.Float()
    company_id = fields.Many2one("res.company")
    user_id = fields.Many2one("res.users", required=True, help="Who deleted it — always the acting user at unlink() time, never sudo's uid.")
    delete_date = fields.Datetime(required=True, default=fields.Datetime.now)

    @api.model
    def log_deletion(self, records, type_key, type_label, label_field="name",
                      partner_field=None, amount_field=None):
        """Called from a tracked model's unlink() override, BEFORE
        super().unlink() actually removes the records — self.create()
        here always runs sudo'd so a salesperson deleting their own
        quotation doesn't need write access to this log model, but
        user_id is still the real acting user (self.env.uid at the
        call site), not the sudo'd uid, so the log stays honest about
        who did it."""
        acting_uid = records.env.uid
        vals_list = []
        for rec in records:
            vals_list.append({
                "res_model": rec._name,
                "res_id": rec.id,
                "type_key": type_key,
                "type_label": type_label,
                "label": getattr(rec, label_field, "") or "",
                "partner": (getattr(rec, partner_field, False).name or "") if partner_field and getattr(rec, partner_field, False) else "",
                "amount": getattr(rec, amount_field, 0) or 0 if amount_field else 0,
                "company_id": getattr(rec, "company_id", False).id if "company_id" in rec._fields and rec.company_id else False,
                "user_id": acting_uid,
            })
        if vals_list:
            self.sudo().create(vals_list)


class SaleOrderDeletionTracking(models.Model):
    _inherit = "sale.order"

    def unlink(self):
        self.env["binget.dashboard.activity.deletion"].log_deletion(
            self, "sale_order", "Sales Order", label_field="name",
            partner_field="partner_id", amount_field="amount_total",
        )
        return super().unlink()


class AccountMoveDeletionTracking(models.Model):
    _inherit = "account.move"

    def unlink(self):
        for move_type, (type_key, type_label) in {
            "out_invoice": ("invoice", "Invoice"),
            "in_invoice": ("bill", "Bill"),
        }.items():
            subset = self.filtered(lambda m, mt=move_type: m.move_type == mt)
            if subset:
                self.env["binget.dashboard.activity.deletion"].log_deletion(
                    subset, type_key, type_label, label_field="name",
                    partner_field="partner_id", amount_field="amount_total",
                )
        return super().unlink()


class PurchaseOrderDeletionTracking(models.Model):
    _inherit = "purchase.order"

    def unlink(self):
        self.env["binget.dashboard.activity.deletion"].log_deletion(
            self, "purchase_order", "Purchase Order", label_field="name",
            partner_field="partner_id", amount_field="amount_total",
        )
        return super().unlink()


class StockPickingDeletionTracking(models.Model):
    _inherit = "stock.picking"

    def unlink(self):
        self.env["binget.dashboard.activity.deletion"].log_deletion(
            self, "stock_picking", "Transfer", label_field="name",
            partner_field="partner_id",
        )
        return super().unlink()


class ResPartnerDeletionTracking(models.Model):
    _inherit = "res.partner"

    def unlink(self):
        self.env["binget.dashboard.activity.deletion"].log_deletion(
            self, "contact", "Contact", label_field="name",
        )
        return super().unlink()


class ProductTemplateDeletionTracking(models.Model):
    _inherit = "product.template"

    def unlink(self):
        self.env["binget.dashboard.activity.deletion"].log_deletion(
            self, "product", "Product", label_field="name",
        )
        return super().unlink()

# NOTE - mrp.production and hr.employee are deliberately NOT overridden
# here: this module only depends on web/sale/stock/account/purchase/
# theme_shell (see __manifest__.py), so Manufacturing and Employees may
# not even be installed on a given database. `_inherit` on a model that
# doesn't exist would break module installation outright. If your
# database has both apps installed, add the same pattern here for
# "mrp.production" (label_field="name") and "hr.employee"
# (label_field="name") once you've confirmed both are always present.
