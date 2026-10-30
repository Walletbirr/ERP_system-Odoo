from odoo import _, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _is_direct_cogs_move(self):
        """Goods going to, or coming back from, a customer (not dropship)."""
        self.ensure_one()
        if 'customer' not in (self.location_id.usage,
                              self.location_dest_id.usage):
            return False
        if self._is_dropshipped() or self._is_dropshipped_returned():
            return False
        return True

    def _get_dest_account(self, accounts_data):
        # Replaces "Stock Interim (Delivered)" with the COGS account on the
        # delivery, and (same method) on the matching return entry.
        if self._is_direct_cogs_move():
            expense = accounts_data.get('expense')
            if expense:
                return expense.id
        return super()._get_dest_account(accounts_data)

    @staticmethod
    def _direct_cogs_sale_reference(order):
        """The CSI number typed on the order. It is the free-text Reference
        added by custom_invoice_management_sale (cim_reference); without that
        module the standard Customer Reference is used."""
        if 'cim_reference' in order._fields:
            return (order.cim_reference or '').strip()
        return (order.client_order_ref or '').strip()

    def _direct_cogs_ref(self, order):
        """"CSI-2456 | WH/OUT/00034", or just the delivery number when the
        order has no CSI."""
        self.ensure_one()
        return ' | '.join(filter(None, [
            self._direct_cogs_sale_reference(order), self.picking_id.name]))

    def _prepare_account_move_vals(self, credit_account_id, debit_account_id,
                                   journal_id, qty, description, svl_id, cost):
        vals = super()._prepare_account_move_vals(
            credit_account_id, debit_account_id, journal_id, qty,
            description, svl_id, cost)
        if not self._is_direct_cogs_move():
            return vals
        sale_line = self.sale_line_id or self.origin_returned_move_id.sale_line_id
        order = sale_line.order_id
        if not order:
            return vals
        partner = order.partner_id.commercial_partner_id or order.partner_id
        product = self.product_id
        label = _(
            "%(kind)s - %(partner)s - Item: %(code)s - %(name)s",
            kind=_("COGS return") if self.env.context.get('is_returned')
            else _("COGS"),
            partner=partner.display_name,
            code=product.default_code or '',
            name=product.name)
        vals['ref'] = self._direct_cogs_ref(order)
        for command in vals['line_ids']:
            command[2]['name'] = label
        return vals
