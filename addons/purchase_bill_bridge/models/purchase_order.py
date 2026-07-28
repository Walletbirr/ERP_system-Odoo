from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    can_create_bill = fields.Boolean(
        compute='_compute_can_create_bill',
        string='Can Create Bill (internal)',
        help='Internal flag: true only for users holding the dedicated '
             '"Purchase Order: Can Create Bill" group, or Settings '
             'Administrators. This is DELIBERATELY NOT tied to the native '
             'Invoicing/Billing access field, because that field cannot '
             'reliably be left blank for every Purchase user on every '
             'instance, and granting it grants the entire Accounting app - '
             'not just this button. Used to hide the native "Create Bill" '
             'button for anyone else, as a second, independent check on '
             'top of the button\'s own "groups" restriction.',
    )

    @api.depends_context('uid')
    def _compute_can_create_bill(self):
        allowed = (
            self.env.user.has_group(
                'purchase_bill_bridge.group_purchase_bill_creator')
            or self.env.user.has_group('base.group_system')
        )
        for order in self:
            order.can_create_bill = allowed
