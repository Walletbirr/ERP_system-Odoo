from odoo import _, api, fields, models


class ShipmentBillWarningWizard(models.TransientModel):
    _name = 'shipment.bill.warning.wizard'
    _description = 'Shipment Arrival Warning — Create Bill'

    purchase_order_ids = fields.Many2many(
        'purchase.order',
        string='Purchase Orders',
    )
    warning_message = fields.Text(
        string='Warning',
        readonly=True,
    )

    def action_proceed(self):
        """User chose to proceed despite no arrived shipment."""
        self.ensure_one()
        return self.purchase_order_ids.with_context(
            skip_shipment_check=True
        ).action_create_invoice()

    def action_cancel(self):
        """User chose to cancel — just close the wizard."""
        return {'type': 'ir.actions.act_window_close'}
