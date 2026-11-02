from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class _DryRun(Exception):
    pass


class CashSaleDraftMigration(models.TransientModel):
    _name = 'cash.sale.draft.migration'
    _description = 'Convert draft invoices to cash sale'

    invoice_ids = fields.Many2many(
        'account.move', string='Draft invoices',
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'draft')]")
    post_after = fields.Boolean(
        string='Post the converted invoices',
        help='Post each converted invoice right away: one journal entry, '
             'bank debited, invoice paid. Leave unticked to only convert '
             'and let Accounting post them after review.')
    payment_term_id = fields.Many2one(
        'account.payment.term', string='Set missing Payment Terms to',
        default=lambda self: self.env['account.payment.term'].search(
            [('name', 'ilike', 'cash')], limit=1),
        help='Old orders created before Payment Terms became required have '
             'none. This term is put on the order and its draft invoice '
             'when they are empty. Orders that already have a term are left '
             'alone. Leave empty to skip.')
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Done')], default='draft')
    report = fields.Text(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get('active_model') == 'account.move' and ctx.get('active_ids'):
            res['invoice_ids'] = [(6, 0, ctx['active_ids'])]
        return res

    def action_load_candidates(self):
        """Every old draft customer invoice whose order is a cash sale."""
        self.ensure_one()
        drafts = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'draft')])
        def wanted(m):
            orders = self._orders(m)
            if len(orders) != 1 or not orders.x_is_cash_sale:
                return False
            if not m.x_is_cash_sale:
                return True
            # already converted: only those still showing fewer banks
            m.x_cash_order_id = m.x_cash_order_id or orders
            banks = len(m._cash_sale_approved_banks())
            lines = len(m.line_ids.filtered(
                lambda l: l.display_type == 'payment_term'))
            return banks > lines
        found = drafts.filtered(wanted)
        self.invoice_ids = [(6, 0, found.ids)]
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name,
            'res_id': self.id, 'view_mode': 'form', 'target': 'new'}

    @staticmethod
    def _orders(inv):
        return inv.sudo().line_ids.sale_line_ids.order_id

    def _check_and_convert(self, inv, post):
        """Convert one invoice. Returns a message; raises UserError to skip."""
        if inv.move_type != 'out_invoice' or inv.state != 'draft':
            raise UserError(_("not a draft customer invoice"))
        orders = self._orders(inv)
        if len(orders) != 1:
            raise UserError(_(
                "linked to %s sales orders (need exactly 1)", len(orders)))
        order = orders
        if not order.x_is_cash_sale:
            raise UserError(_(
                "order %s is not a cash sale (payment term: %s)",
                order.name, order.payment_term_id.display_name or '-'))
        term_note = ''
        if self.payment_term_id and not order.payment_term_id:
            order.sudo().write({'payment_term_id': self.payment_term_id.id})
            term_note = _(", term set to %s", self.payment_term_id.name)
        if self.payment_term_id and not inv.invoice_payment_term_id:
            inv.invoice_payment_term_id = self.payment_term_id
        already = inv.x_is_cash_sale
        inv.write({'x_is_cash_sale': True, 'x_cash_order_id': order.id})
        rows = inv._cash_sale_approved_banks()
        if not rows:
            raise UserError(_(
                "order %s has no approved payment proof with a bank",
                order.name))
        currency = inv.currency_id
        rows = inv._cash_sale_bank_rows()
        total = sum(a for _j, a in rows)
        if currency.compare_amounts(total, inv.amount_total):
            raise UserError(_(
                "approved banks (%(banks)s) do not match the invoice total "
                "(%(total)s)",
                banks=formatLang(self.env, total, currency_obj=currency),
                total=formatLang(self.env, inv.amount_total,
                                 currency_obj=currency)))
        inv._cash_sale_apply_banks(strict=False)
        banks = ', '.join(
            '%s %s' % (j.name, formatLang(self.env, a, currency_obj=currency))
            for j, a in inv._cash_sale_bank_rows())
        if post:
            inv.action_post()
            return _("converted and POSTED (%(bank)s)", bank=banks) + term_note
        return _("converted to draft cash sale (%(bank)s)", bank=banks) + term_note

    def _run(self, dry_run):
        self.ensure_one()
        if not self.invoice_ids:
            raise UserError(_("Select at least one draft invoice."))
        lines, ok = [], 0
        for inv in self.invoice_ids.sorted('id'):
            label = '%s [%s] %s' % (
                inv.name if inv.name and inv.name != '/' else 'Draft',
                inv.id, inv.partner_id.display_name or '')
            try:
                with self.env.cr.savepoint():
                    msg = self._check_and_convert(
                        inv, self.post_after and not dry_run)
                    if dry_run:
                        raise _DryRun(msg)
                lines.append('OK    %s: %s' % (label, msg))
                ok += 1
            except _DryRun as e:
                self.env.invalidate_all()
                lines.append('OK    %s: would be %s' % (label, e))
                ok += 1
            except Exception as e:  # skip, never stop the batch
                self.env.invalidate_all()
                lines.append('SKIP  %s: %s' % (
                    label, getattr(e, 'args', [str(e)])[0]))
        head = '%s: %d OK, %d skipped of %d invoice(s)\n' % (
            'CHECK ONLY - nothing changed' if dry_run else 'DONE',
            ok, len(self.invoice_ids) - ok, len(self.invoice_ids))
        self.write({'report': head + '\n'.join(lines),
                    'state': 'done' if not dry_run else 'draft'})
        return self._reopen()

    def action_check(self):
        return self._run(dry_run=True)

    def action_convert(self):
        return self._run(dry_run=False)
