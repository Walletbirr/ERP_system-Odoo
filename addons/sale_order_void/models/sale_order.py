from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import plaintext2html

VOID_GROUP = 'sale_order_void.group_sale_void'
# status names a payment-proof model may use for "not valid any more"
PROOF_VOID_STATES = ('void', 'voided', 'cancel', 'cancelled', 'canceled',
                     'rejected')


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'sale.void.mixin']

    x_void_status = fields.Selection(
        [('draft', 'Quotation'), ('sent', 'Quotation Sent'),
         ('sale', 'Sales Order'), ('done', 'Locked'),
         ('cancel', 'Cancelled'), ('void', 'Void')],
        string='Status', compute='_compute_x_void_status')

    @api.depends('x_is_voided', 'state')
    def _compute_x_void_status(self):
        keys = ('draft', 'sent', 'sale', 'done', 'cancel')
        for order in self:
            order.x_void_status = (
                'void' if order.x_is_voided
                else (order.state if order.state in keys else False))

    # ------------------------------------------------------------------
    # What will be reversed
    # ------------------------------------------------------------------
    def _void_plan(self):
        """Everything the void will touch, as recordsets. Read only."""
        self.ensure_one()
        order = self.sudo()
        invoices = order.invoice_ids
        posted = invoices.filtered(lambda m: m.state == 'posted')
        drafts = invoices.filtered(lambda m: m.state == 'draft')

        receivable = posted.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable')
        partials = receivable.matched_debit_ids | receivable.matched_credit_ids
        counterpart_moves = (
            (partials.debit_move_id | partials.credit_move_id).move_id
            - posted)
        payments = self.env['account.payment'].sudo().search([
            ('move_id', 'in', counterpart_moves.ids),
            ('state', 'not in', ('draft', 'canceled', 'rejected', 'void')),
        ])

        # A payment is voided only when it was used ONLY by this order's
        # invoices and nothing of it is left over. Any other payment is just
        # unreconciled and stays as customer credit.
        to_void = payments.browse()
        to_keep = payments.browse()
        for pay in payments:
            pay_receivable = pay.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable')
            pay_partials = (pay_receivable.matched_debit_ids
                            | pay_receivable.matched_credit_ids)
            others = ((pay_partials.debit_move_id | pay_partials.credit_move_id)
                      .move_id - pay.move_id)
            company_currency = pay.company_id.currency_id
            fully_used = all(company_currency.is_zero(l.amount_residual)
                             for l in pay_receivable)
            if others <= posted and fully_used:
                to_void |= pay
            else:
                to_keep |= pay

        if 'picking_ids' in order._fields:
            pickings = order.picking_ids
        else:
            pickings = self.env['stock.picking']
        proofs = (order.payment_proof_ids
                  if 'payment_proof_ids' in order._fields
                  else self.env['account.move'].browse())
        return {
            'receivable_lines': receivable,
            'posted_moves': posted,
            'draft_moves': drafts,
            'pay_void': to_void,
            'pay_keep': to_keep,
            'deliveries_done': pickings.filtered(
                lambda p: p.state == 'done'
                and p.picking_type_code == 'outgoing'),
            'deliveries_open': pickings.filtered(
                lambda p: p.state not in ('done', 'cancel')),
            'proofs': proofs,
        }

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type in ('list', 'tree'):
            self._void_patch_list_status(
                arch,
                success="x_void_status in ('sale', 'done')",
                info="x_void_status in ('draft', 'sent')")
        return arch, view

    @api.model
    def _void_proof_label(self, proof):
        name = proof._fields.get('name') and proof.name
        return '%s (%s)' % (name or '#%s' % proof.id,
                            getattr(proof, 'state', '') or '-')

    def _void_summary(self):
        self.ensure_one()
        order = self.sudo()
        plan = order._void_plan()
        kind = _("Cash sale") if getattr(order, 'x_is_cash_sale', False) \
            else _("Credit sale")
        names = lambda recs: ', '.join(recs.mapped('display_name')) or '-'
        lines = [
            _("%(order)s (%(kind)s)", order=order.name, kind=kind),
            _("Invoices / credit notes to cancel: %s",
              names(plan['posted_moves'] | plan['draft_moves'])),
            _("Payments to mark VOID: %s", names(plan['pay_void'])),
            _("Payments kept as customer credit (shared or with an unused "
              "balance): %s", names(plan['pay_keep'])),
            (_("Deliveries to reverse in place (stock and valuation "
               "restored, then cancelled): %s", names(plan['deliveries_done']))
             if order._void_can_reverse_in_place()
             else _("Deliveries to return: %s",
                    names(plan['deliveries_done']))),
            _("Deliveries to cancel: %s", names(plan['deliveries_open'])),
            _("Payment proofs: %s", ', '.join(
                order._void_proof_label(p) for p in plan['proofs']) or '-'),
        ]
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_open_void_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Void Sale"),
            'res_model': 'sale.order.void.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def action_draft(self):
        if any(o.x_is_voided for o in self):
            raise UserError(_("A voided sales order cannot be set back to "
                              "quotation. Create a new quotation instead."))
        return super().action_draft()

    # ------------------------------------------------------------------
    # The void itself (one transaction: all or nothing)
    # ------------------------------------------------------------------
    def _void_execute(self, reason):
        self.ensure_one()
        if not self.env.user.has_group(VOID_GROUP):
            raise AccessError(_("You are not allowed to void sales orders."))
        if self.x_is_voided:
            raise UserError(_("%s is already void.", self.name))
        if self.state != 'sale':
            raise UserError(_(
                "Only a confirmed sales order can be voided. %s is not "
                "confirmed (use Cancel for quotations).", self.name))
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_("Write the reason for the void."))

        order = self.sudo().with_context(
            sale_order_void=True, disable_cancel_warning=True)
        plan = order._void_plan()
        log = []

        # 1. unreconcile everything that is reconciled with the invoices
        plan['receivable_lines'].remove_move_reconcile()

        # 2. payments
        for pay in plan['pay_void']:
            order._void_payment(pay, reason)
            log.append(_("Payment %s set to VOID", pay.display_name))
        for pay in plan['pay_keep']:
            pay.message_post(body=_(
                "Unreconciled from %s because the order was voided. The "
                "payment is kept as customer credit.", order.name))
            log.append(_("Payment %s kept as customer credit",
                         pay.display_name))

        # 3. invoices and credit notes (credit notes first)
        moves = plan['posted_moves'] | plan['draft_moves']
        for move in moves.sorted(
                key=lambda m: (m.move_type != 'out_refund', m.id)):
            how = order._void_move(move, reason)
            log.append(_("%(kind)s %(name)s %(how)s",
                         kind=_("Credit note") if move.move_type == 'out_refund'
                         else _("Invoice"),
                         name=move.display_name, how=how))

        # 4. deliveries
        for picking in plan['deliveries_open']:
            picking.action_cancel()
            log.append(_("Delivery %s cancelled", picking.display_name))
        for picking in plan['deliveries_done']:
            log.append(order._void_reverse_delivery(picking, reason))

        # 5. payment proofs
        log += order._void_payment_proofs(plan['proofs'])

        # 6. the sales order
        order._action_cancel()
        if order.state != 'cancel':
            raise UserError(_("%s could not be cancelled.", order.name))
        order.write(order._void_flag_values(reason))
        order.message_post(body=plaintext2html(
            _("VOID. Reason: %s", reason) + '\n' + '\n'.join(log)))
        return True

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    def _void_payment(self, pay, reason):
        """Same result as ticking Void on a manual payment: zero value entry,
        status Void, voucher number kept."""
        self.ensure_one()
        original = pay.amount
        try:
            pay.write({'x_void_original_amount': original})
            pay.action_draft()
            pay.write({'is_void': True, 'is_multi_line': False})
            pay.action_post()
        except UserError as err:
            raise UserError(_(
                "Payment %(pay)s could not be voided: %(err)s\n"
                "If it is matched with a bank statement line, unmatch it "
                "first.", pay=pay.display_name, err=err.args[0])) from err
        if pay.state != 'void':
            raise UserError(_(
                "Payment %s did not reach the Void status.",
                pay.display_name))
        pay.write(dict(self._void_flag_values(reason),
                       x_void_order_id=self.id))
        pay.message_post(body=_(
            "Voided with sales order %(order)s. Amount before void: "
            "%(amount)s. Reason: %(reason)s",
            order=self.name,
            amount=pay.currency_id.format(original), reason=reason))

    def _void_move(self, move, reason):
        """Cancel an invoice / credit note. Returns a short text for the log."""
        self.ensure_one()
        journal = move.journal_id
        hashed = (getattr(journal, 'restrict_mode_hash_table', False)
                  and getattr(move, 'inalterable_hash', False))
        flags = dict(self._void_flag_values(reason), x_void_order_id=self.id)
        try:
            if hashed and move.state == 'posted':
                reversal = move._reverse_moves(
                    [{'ref': _("Void of %s", move.name)}], cancel=True)
                (move | reversal).write(flags)
                reversal.message_post(body=_(
                    "Reversal created by the void of %s.", self.name))
                how = _("reversed by %s", reversal.display_name)
            else:
                if move.state == 'posted':
                    move.button_draft()
                move.button_cancel()
                move.write(flags)
                how = _("cancelled")
        except UserError as err:
            raise UserError(_(
                "%(doc)s could not be voided: %(err)s",
                doc=move.display_name, err=err.args[0])) from err
        move.message_post(body=_(
            "Voided with sales order %(order)s. Reason: %(reason)s",
            order=self.name, reason=reason))
        return how

    @api.model
    def _void_can_reverse_in_place(self):
        """True when the Delivery Set to Draft module is installed."""
        return hasattr(self.env['stock.picking'], '_set_to_draft_and_revert')

    def _void_reverse_delivery(self, picking, reason):
        """Undo a done delivery. Preferred: reverse it IN PLACE with the
        Delivery Set to Draft module (same delivery, stock and valuation
        restored, then cancelled) so the history stays on the sale's own
        delivery. Fallback: a validated return picking."""
        self.ensure_one()
        already_returned = picking.move_ids.returned_move_ids.filtered(
            lambda m: m.state != 'cancel')
        if self._void_can_reverse_in_place() and not already_returned:
            try:
                picking._set_to_draft_and_revert()
                picking.action_cancel()
            except UserError as err:
                raise UserError(_(
                    "Delivery %(pick)s could not be reversed: %(err)s",
                    pick=picking.display_name, err=err.args[0])) from err
            if picking.state != 'cancel':
                raise UserError(_(
                    "Delivery %s could not be cancelled after the reversal.",
                    picking.display_name))
            picking.message_post(body=_(
                "Reversed and cancelled with the void of sales order "
                "%(order)s: stock and valuation restored. Reason: %(reason)s",
                order=self.name, reason=reason))
            return _("Delivery %s reversed in place and cancelled",
                     picking.display_name)
        back = self._void_return_picking(picking)
        if not back:
            return _("Delivery %s was already returned", picking.display_name)
        return _("Delivery %(done)s returned with %(back)s",
                 done=picking.display_name, back=back.display_name)

    def _void_return_picking(self, picking):
        """Return what was delivered and validate the return."""
        self.ensure_one()
        wizard = self.env['stock.return.picking'].with_context(
            active_id=picking.id, active_ids=picking.ids,
            active_model='stock.picking').create({})
        wizard.product_return_moves.filtered(
            lambda l: l.quantity <= 0).unlink()
        if not wizard.product_return_moves:
            return None  # already returned
        res = wizard._create_returns()
        back_id = res[0] if isinstance(res, (tuple, list)) else res
        back = self.env['stock.picking'].browse(back_id)
        if back.state == 'draft':
            back.action_confirm()
        back.action_assign()
        for move in back.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')):
            if not move.quantity:
                move.quantity = move.product_uom_qty
            move.picked = True
        res = back.with_context(
            skip_immediate=True, skip_backorder=True, skip_sms=True,
        ).button_validate()
        if isinstance(res, dict) or back.state != 'done':
            raise UserError(_(
                "The return %(back)s of %(done)s could not be validated "
                "automatically (lots / serial numbers?). Validate it by "
                "hand, then void the order again.",
                back=back.display_name, done=picking.display_name))
        return back

    def _void_payment_proofs(self, proofs):
        """Mark the order's payment proofs void when the proof model has a
        suitable status. Returns log lines."""
        self.ensure_one()
        log = []
        for proof in proofs:
            field = proof._fields.get('state')
            if field is None or field.compute:
                log.append(_("Payment proof %s: check it by hand",
                             self._void_proof_label(proof)))
                continue
            options = [key for key, _label in field._description_selection(
                self.env)]
            target = next((s for s in PROOF_VOID_STATES if s in options), None)
            if not target:
                log.append(_("Payment proof %s: no void status, check it "
                             "by hand", self._void_proof_label(proof)))
                continue
            proof.write({'state': target})
            log.append(_("Payment proof %(name)s set to %(state)s",
                         name=self._void_proof_label(proof), state=target))
        return log
