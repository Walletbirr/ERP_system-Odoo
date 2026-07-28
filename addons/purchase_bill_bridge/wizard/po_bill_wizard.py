from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountPoBillWizard(models.TransientModel):
    """
    Lets a Billing/Accountant user (who has NO Purchase module access) pick a
    CONFIRMED Purchase Order, preview what will be billed, and generate the
    Vendor Bill.

    Odoo 18 moved away from a single stable "create bill" method on
    purchase.order, so this wizard creates the account.move (Vendor Bill)
    directly and pulls the PO lines in via _add_purchase_order_lines() -
    the same helper the native "Auto-Complete" field on a Vendor Bill uses.
    If that helper isn't present on a given build, it falls back to a plain
    line-by-line copy so the wizard still works.
    """
    _name = 'account.po.bill.wizard'
    _description = 'Create Vendor Bill from Purchase Order'

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        # Only confirmed orders that still have something left to bill.
        domain=[('state', '=', 'purchase'), ('invoice_status', '=', 'to invoice')],
        help='Only confirmed Purchase Orders with an outstanding amount to '
             'bill are shown here. Draft/sent RFQs are never visible.',
    )
    partner_id = fields.Many2one(
        related='purchase_order_id.partner_id', string='Vendor', readonly=True)
    currency_id = fields.Many2one(
        related='purchase_order_id.currency_id', readonly=True)
    amount_total = fields.Monetary(
        related='purchase_order_id.amount_total', readonly=True,
        string='Order Total')
    invoice_status = fields.Selection(
        related='purchase_order_id.invoice_status', readonly=True)
    preview_line_ids = fields.Many2many(
        'purchase.order.line',
        compute='_compute_preview_lines',
        string='Order Lines (preview)',
    )

    @api.depends('purchase_order_id')
    def _compute_preview_lines(self):
        for wizard in self:
            wizard.preview_line_ids = (
                wizard.purchase_order_id.order_line
                if wizard.purchase_order_id else False
            )

    def _fallback_bill_lines(self, order):
        """Plain copy of PO lines onto invoice_line_ids, used only if
        _add_purchase_order_lines is not available on this build."""
        lines = []
        for line in order.order_line:
            qty_to_bill = line.product_qty - line.qty_invoiced
            if qty_to_bill <= 0:
                continue
            lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'quantity': qty_to_bill,
                'price_unit': line.price_unit,
                'tax_ids': [(6, 0, line.taxes_id.ids)],
                'purchase_line_id': line.id,
            }))
        return lines

    def action_create_bill(self):
        self.ensure_one()
        order = self.purchase_order_id
        if not order:
            raise UserError("Please select a Purchase Order first.")
        if order.invoice_status != 'to invoice':
            raise UserError(
                "This Purchase Order has nothing left to bill. It may "
                "already be fully billed."
            )

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': order.partner_id.id,
            'invoice_origin': order.name,
            'partner_ref': order.partner_ref or order.name,
        })

        if hasattr(bill, '_add_purchase_order_lines'):
            bill._add_purchase_order_lines(order.order_line)
        else:
            bill.write({'invoice_line_ids': self._fallback_bill_lines(order)})

        action = self.env['ir.actions.actions']._for_xml_id(
            'account.action_move_in_invoice_type')
        action['views'] = [(False, 'form')]
        action['res_id'] = bill.id
        return action
