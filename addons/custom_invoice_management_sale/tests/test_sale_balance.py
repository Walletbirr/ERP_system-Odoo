# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestSaleBalance(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Tax = cls.env['account.tax']
        cls.excise = Tax.create({
            'name': 'Excise 10', 'amount': 10, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'include_base_amount': True, 'sequence': 1,
        })
        cls.vat = Tax.create({
            'name': 'VAT 15', 'amount': 15, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'sequence': 2,
        })
        cls.wht = Tax.create({
            'name': 'WHT 2', 'amount': -2, 'amount_type': 'percent',
            'type_tax_use': 'sale', 'sequence': 3,
        })
        cls.car = cls.env['product.product'].create({
            'name': 'Car', 'type': 'consu', 'list_price': 380000.0,
            'taxes_id': [(6, 0, (cls.excise | cls.vat).ids)],
        })
        cls.car2 = cls.env['product.product'].create({
            'name': 'Truck', 'type': 'consu', 'list_price': 100000.0,
            'taxes_id': [(6, 0, (cls.excise | cls.vat).ids)],
        })
        cls.service = cls.env.ref('custom_invoice_management.product_service_charge')
        cls.income = cls.env['account.account'].search([
            ('account_type', '=', 'income_other'),
            ('company_ids', 'in', cls.env.company.id)], limit=1) or cls.env['account.account'].search([
            ('account_type', '=', 'income'), ('company_ids', 'in', cls.env.company.id)], limit=1)
        cls.env.company.cim_service_charge_account_id = cls.income
        cls.partner = cls.env['res.partner'].create({'name': 'Customer X'})

    def _order(self, products=None, price=490000.0, auto=True):
        """Quotation with a Selling Price on its first line. With auto=False
        the automatic balance is switched off to build an unbalanced order."""
        products = products or self.car
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': p.id, 'product_uom_qty': 1}) for p in products],
        })
        ctx = {} if auto else {'cim_skip_auto_balance': True}
        order.order_line[0].with_context(**ctx).cim_selling_price = price
        return order

    def _service_lines(self, order):
        return order.order_line.filtered(lambda l: l.product_id == self.service)

    # ------------------------------------------------------------------
    def test_service_product_is_labelled_other_income(self):
        self.assertEqual(self.service.name, 'Other Income')

    def test_auto_balance_on_selling_price(self):
        """No Balance button: writing the Selling Price is enough."""
        order = self._order()
        svc = self._service_lines(order)
        self.assertEqual(len(svc), 1)
        self.assertAlmostEqual(order.amount_total, 490000.0, 2)
        self.assertEqual(svc.name, 'Other Income')
        self.assertTrue(svc.cim_hide_from_order_lines)
        self.assertEqual(svc.tax_id, self.vat)
        self.assertEqual(order.order_line[0].cim_service_line_id, svc)
        # custom totals box
        self.assertAlmostEqual(order.cim_product_untaxed_amount, 380000.0, 2)
        self.assertAlmostEqual(order.cim_excise_tax_amount, 38000.0, 2)
        self.assertAlmostEqual(order.cim_subtotal_before_vat, 418000.0, 2)
        self.assertAlmostEqual(order.cim_service_charge_amount, 8086.96, 2)
        self.assertAlmostEqual(order.cim_before_vat_amount, 426086.96, 2)
        self.assertAlmostEqual(order.cim_vat_amount, 63913.04, 2)
        self.assertAlmostEqual(order.cim_wht_amount, 0.0, 2)

    def test_auto_balance_on_create(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.car.id,
                'product_uom_qty': 1,
                'cim_selling_price': 490000.0,
            })],
        })
        self.assertEqual(len(self._service_lines(order)), 1)
        self.assertAlmostEqual(order.amount_total, 490000.0, 2)

    def test_auto_balance_through_order_write(self):
        """What the web client sends on save: order.write with line commands."""
        order = self._order(price=0.0)
        self.assertAlmostEqual(order.amount_total, 480700.0, 2)
        line = order.order_line[0]
        order.write({'order_line': [(1, line.id, {'cim_selling_price': 490000.0})]})
        self.assertEqual(len(self._service_lines(order)), 1)
        self.assertAlmostEqual(order.amount_total, 490000.0, 2)

    def test_manual_balance_still_works(self):
        order = self._order(auto=False)
        self.assertFalse(self._service_lines(order))
        self.assertAlmostEqual(order.amount_total, 480700.0, 2)
        order.action_cim_balance()
        self.assertEqual(len(self._service_lines(order)), 1)
        self.assertAlmostEqual(order.amount_total, 490000.0, 2)

    def test_rebalance_updates_same_line(self):
        order = self._order()
        svc = self._service_lines(order)
        order.order_line[0].cim_selling_price = 495000.0
        self.assertEqual(self._service_lines(order), svc)
        self.assertAlmostEqual(order.amount_total, 495000.0, 2)
        order.action_cim_balance()   # idempotent
        self.assertEqual(len(self._service_lines(order)), 1)
        self.assertAlmostEqual(order.amount_total, 495000.0, 2)

    def test_price_change_keeps_total(self):
        order = self._order()
        order.order_line[0].price_unit = 370000.0
        self.assertEqual(len(self._service_lines(order)), 1)
        self.assertAlmostEqual(order.amount_total, 490000.0, 2)

    def test_clearing_selling_price_removes_service_line(self):
        order = self._order()
        line = order.order_line[0]
        line.cim_selling_price = 0.0
        self.assertFalse(self._service_lines(order))
        self.assertFalse(line.cim_service_line_id)
        self.assertAlmostEqual(order.amount_total, 480700.0, 2)

    def test_lower_selling_price_raises(self):
        with self.assertRaises(UserError):
            self._order(price=100000.0)

    def test_no_selling_price_is_silent_but_manual_balance_raises(self):
        order = self._order(price=0.0)
        self.assertFalse(self._service_lines(order))
        self.assertAlmostEqual(order.amount_total, 480700.0, 2)
        with self.assertRaises(UserError):
            order.action_cim_balance()

    def test_two_lines_independent_and_clear(self):
        order = self._order(products=self.car | self.car2)
        l1, l2 = order.order_line[0], order.order_line[1]
        l2.cim_selling_price = 130000.0
        self.assertEqual(len(self._service_lines(order)), 2)
        self.assertAlmostEqual(order.amount_total, 490000.0 + 130000.0, 2)
        l1.cim_selling_price = 0.0
        self.assertEqual(len(self._service_lines(order)), 1)
        self.assertFalse(l1.cim_service_line_id)
        self.assertAlmostEqual(order.amount_total, 480700.0 + 130000.0, 2)

    def test_withholding_tax_is_not_part_of_selling_price(self):
        self.car.taxes_id = [(6, 0, (self.excise | self.vat | self.wht).ids)]
        order = self._order()
        self.assertEqual(self._service_lines(order).tax_id, self.vat | self.wht)
        self.assertTrue(order.cim_wht_amount < 0)
        self.assertAlmostEqual(order.cim_total_before_wht, 490000.0, 1)

    def test_confirm_requires_selling_price(self):
        order = self._order(price=0.0)
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, 'draft')
        order.order_line[0].cim_selling_price = 490000.0
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_confirm_requires_selling_price_on_every_line(self):
        order = self._order(products=self.car | self.car2)   # only line 1 has one
        with self.assertRaises(UserError):
            order.action_confirm()
        order.order_line.filtered(lambda l: l.product_id == self.car2).cim_selling_price = 130000.0
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_locked_state_blocks_manual_balance_and_skips_auto(self):
        order = self._order()
        order.action_confirm()
        with self.assertRaises(UserError):
            order.action_cim_balance()
        # Confirmed orders are never re-balanced behind the user's back.
        order.order_line[0].cim_selling_price = 500000.0
        self.assertAlmostEqual(order.amount_total, 490000.0, 2)

    def test_deleting_product_line_deletes_service_line(self):
        order = self._order(products=self.car | self.car2)
        self.assertEqual(len(self._service_lines(order)), 1)
        order.order_line.filtered(lambda l: l.product_id == self.car).unlink()
        self.assertFalse(self._service_lines(order))
        self.assertEqual(len(order.order_line), 1)

    def test_duplicate_keeps_balance(self):
        order = self._order()
        new = order.copy()
        self.assertAlmostEqual(new.amount_total, 490000.0, 2)
        self.assertEqual(len(self._service_lines(new)), 1)
        self.assertEqual(new.order_line.filtered(
            lambda l: l.product_id == self.car).cim_service_line_id, self._service_lines(new))
        new.action_cim_balance()
        self.assertEqual(len(self._service_lines(new)), 1)
        self.assertAlmostEqual(new.amount_total, 490000.0, 2)

    def test_order_to_invoice(self):
        order = self._order()
        order.action_confirm()
        inv = order._create_invoices()
        self.assertEqual(len(inv), 1)
        self.assertAlmostEqual(inv.amount_total, 490000.0, 2)
        svc_inv = inv.invoice_line_ids.filtered(lambda l: l.product_id == self.service)
        self.assertEqual(len(svc_inv), 1)
        self.assertEqual(svc_inv.account_id, self.income)
        self.assertTrue(svc_inv.cim_hide_from_invoice_lines)
        prod_inv = inv.invoice_line_ids.filtered(lambda l: l.product_id == self.car)
        # selling price and link carried over
        self.assertAlmostEqual(prod_inv.cim_selling_price, 490000.0, 2)
        self.assertEqual(prod_inv.cim_service_line_id, svc_inv)
        # the accounting module's own totals box agrees with the sales one
        self.assertAlmostEqual(inv.cim_service_charge_amount, order.cim_service_charge_amount, 2)
        self.assertAlmostEqual(inv.cim_vat_amount, order.cim_vat_amount, 2)
        self.assertAlmostEqual(inv.cim_excise_tax_amount, order.cim_excise_tax_amount, 2)
        # Balance on the invoice must update, not duplicate
        inv.action_cim_balance()
        self.assertEqual(len(inv.invoice_line_ids.filtered(lambda l: l.product_id == self.service)), 1)
        self.assertAlmostEqual(inv.amount_total, 490000.0, 2)
        # and the invoice can be posted
        inv.action_post()
        self.assertEqual(inv.state, 'posted')

    def test_view_and_report(self):
        order = self._order()
        view = order.get_view(self.env.ref('sale.view_order_form').id, 'form')
        self.assertIn('cim_selling_price', view['arch'])
        self.assertNotIn('action_cim_balance', view['arch'])   # no Balance button
        # Other Income / Before Vat rows are never hidden, even before balancing
        self.assertNotIn('invisible="not cim_service_charge_amount"', view['arch'])
        self.assertIn('cim_hide_from_order_lines', view['arch'])
        html, _ = self.env['ir.actions.report']._render_qweb_html('sale.action_report_saleorder', order.ids)
        html = html.decode()
        self.assertIn('From (Seller)', html)
        self.assertIn('To (Buyer)', html)
        self.assertIn('Customer X', html)
        self.assertIn('Other Income', html)
