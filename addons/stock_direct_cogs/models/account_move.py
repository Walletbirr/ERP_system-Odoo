from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _stock_account_prepare_anglo_saxon_out_lines_vals(self):
        """Customer invoices no longer add the COGS / Stock Interim
        (Delivered) pair: the delivery already posted COGS against Inventory.
        Vendor bills and purchase valuation are not affected."""
        return []
