from odoo.exceptions import UserError
from odoo.tests import Form, tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestManualJournalItems(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Customer'})
        cls.income = cls.env['account.account'].search(
            [('account_type', '=', 'income'), ('company_ids', 'in', cls.company.id)], limit=1)
        user = cls.env['res.users'].create({
            'name': 'Accountant', 'login': 'acc_ile',
            'groups_id': [(6, 0, [
                cls.env.ref('account.group_account_manager').id,
                cls.env.ref('account.group_account_user').id,
                cls.env.ref('account.group_account_readonly').id,
                cls.env.ref('base.group_user').id,
            ])],
        })
        cls.env = cls.env(user=user)
        cls.partner = cls.partner.with_env(cls.env)
        cls.income = cls.income.with_env(cls.env)

    def _invoice(self):
        tax = self.env['account.tax'].search(
            [('type_tax_use', '=', 'sale'), ('amount', '=', 15),
             ('company_id', '=', self.company.id)], limit=1)
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': '2026-10-31',
            'invoice_line_ids': [(0, 0, {
                'name': 'Widget', 'quantity': 1, 'price_unit': 1000.0,
                'tax_ids': [(6, 0, tax.ids)],
                'account_id': self.income.id,
            })],
        })

    def _term(self, move):
        return move.line_ids.filtered(lambda l: l.display_type == 'payment_term')

    def _add_line(self, move, credit):
        form = Form(move)
        with form.line_ids.new() as line:
            line.account_id = self.income
            line.name = 'Extra'
            line.credit = credit
        form.save()

    def test_form_is_patched(self):
        arch = self.env['account.move'].get_view(view_type='form')['arch']
        self.assertIn('manual_journal_items', arch)
        self.assertNotIn('action_balance_manual_entry', arch)

    def test_typed_receivable_is_kept_and_posts(self):
        move = self._invoice()
        move.manual_journal_items = True
        self.assertEqual(self._term(move).debit, 1150.0)
        form = Form(move)
        with form.line_ids.new() as line:
            line.account_id = self.income
            line.name = 'Service charge'
            line.credit = 12.0
        idx = [i for i, l in enumerate(move.line_ids) if l.display_type == 'payment_term'][0]
        with form.line_ids.edit(index=idx) as line:
            line.debit = 1162.0
        form.save()
        self.assertEqual(self._term(move).debit, 1162.0)
        move.action_post()
        self.assertEqual(move.state, 'posted')

    def test_unbalanced_gives_clear_message(self):
        move = self._invoice()
        move.manual_journal_items = True
        with self.assertRaises(UserError) as cm:
            self._add_line(move, 12.0)
        self.assertIn('differ by', str(cm.exception))

    def test_untick_restores_automatic_calculation(self):
        move = self._invoice()
        move.manual_journal_items = True
        move.manual_journal_items = False
        move.invoice_line_ids.price_unit = 2000.0
        self.assertEqual(self._term(move).debit, 2300.0)

    def test_standard_invoices_are_untouched(self):
        move = self._invoice()
        self.assertFalse(move.manual_journal_items)
        move.invoice_line_ids.price_unit = 2000.0
        self.assertEqual(self._term(move).debit, 2300.0)

    def test_cim_auto_balance_does_not_rewrite_manual_invoice(self):
        if 'cim_selling_price' not in self.env['account.move.line']._fields:
            self.skipTest('custom_invoice_management not installed')
        move = self._invoice()
        move.manual_journal_items = True
        before = move.line_ids.mapped('balance')
        move.invoice_line_ids.write({'cim_selling_price': 1200.0})
        self.assertEqual(move.line_ids.mapped('balance'), before)

    def test_zero_amount_currency_from_web_form_does_not_zero_the_line(self):
        """The web client sends amount_currency=0 with a typed credit."""
        move = self._invoice()
        move.manual_journal_items = True
        term = self._term(move)
        move.write({'line_ids': [
            (1, term.id, {'debit': 1160.0, 'balance': 1160.0}),
            (0, 0, {'account_id': self.income.id, 'name': 'Bank charge',
                    'credit': 10, 'debit': 0, 'balance': -10,
                    'amount_currency': 0, 'tax_ids': [],
                    'display_type': 'product'}),
        ]})
        extra = move.line_ids.filtered(lambda l: l.name == 'Bank charge')
        self.assertEqual(extra.credit, 10.0)
        move.action_post()
        self.assertEqual(move.state, 'posted')

    def test_manual_line_is_flagged_and_hidden_from_invoice_lines_tab(self):
        move = self._invoice()
        move.manual_journal_items = True
        term = self._term(move)
        move.write({'line_ids': [
            (1, term.id, {'debit': 1160.0, 'balance': 1160.0}),
            (0, 0, {'account_id': self.income.id, 'name': 'Bank charge',
                    'credit': 10, 'debit': 0, 'balance': -10,
                    'amount_currency': 0, 'tax_ids': [],
                    'display_type': 'product'}),
        ]})
        extra = move.line_ids.filtered(lambda l: l.name == 'Bank charge')
        self.assertTrue(extra.ile_manual_line)
        self.assertFalse(move.invoice_line_ids.filtered('ile_manual_line') - extra)
        self.assertIn(extra, move.line_ids)
        if 'cim_invoice_line_ids_display' in move._fields:
            self.assertNotIn(extra, move.cim_invoice_line_ids_display)
            self.assertTrue(move.cim_invoice_line_ids_display)  # real lines stay
        # the normal invoice line is not flagged
        self.assertFalse(move.invoice_line_ids.filtered(lambda l: l.name == 'Widget').ile_manual_line)

    def test_receivable_line_can_be_deleted_and_replaced(self):
        move = self._invoice()
        move.manual_journal_items = True
        term = self._term(move)
        move.write({'line_ids': [
            (2, term.id),
            (0, 0, {'account_id': self.income.id, 'name': 'Replacement',
                    'debit': 1150.0, 'credit': 0, 'balance': 1150.0,
                    'display_type': 'product'}),
        ]})
        self.assertFalse(self._term(move))
        move.action_post()
        self.assertEqual(move.state, 'posted')
