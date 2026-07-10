from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    can_create_invoice = fields.Boolean(
        compute='_compute_can_create_invoice',
        string='Can Create Invoice (internal)',
        help='Internal flag: true only for users holding the dedicated '
             '"Sales Order: Can Create Invoice" group, or Settings '
             'Administrators. This is DELIBERATELY NOT tied to the native '
             'Invoicing/Billing access field, because that field cannot '
             'reliably be left blank for every Sales user on every '
             'instance, and granting it grants the entire Accounting app - '
             'not just this button. Used to hide the native "Create '
             'Invoice" button for anyone else, as a second, independent '
             'check on top of the button\'s own "groups" restriction.',
    )

    @api.depends_context('uid')
    def _compute_can_create_invoice(self):
        allowed = (
            self.env.user.has_group(
                'accounting_so_invoice_bridge.group_sale_invoice_creator')
            or self.env.user.has_group('base.group_system')
        )
        for order in self:
            order.can_create_invoice = allowed
