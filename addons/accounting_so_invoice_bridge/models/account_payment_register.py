import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.model
    def _proof_journal_for_moves(self, moves):
        """Journal the accountant chose when approving the payment proof of
        the order(s) behind these customer invoices. With several approved
        proofs the most recently approved one wins. Empty if none or if the
        journal can not be used for this payment."""
        moves = moves.filtered(
            lambda m: m.move_type == 'out_invoice').sudo()
        proofs = moves.x_sale_order_ids.payment_proof_ids.filtered(
            lambda p: p.state == 'approved' and p.payment_journal_id)
        if not proofs:
            return self.env['account.journal']
        journal = proofs.sorted(
            lambda p: (p.reviewed_date or p.create_date, p.id)
        )[-1].payment_journal_id
        if journal.type not in ('bank', 'cash') \
                or journal.company_id != moves[:1].company_id:
            return self.env['account.journal']
        lines_of = getattr(journal, '_get_available_payment_method_lines', None)
        if lines_of and not lines_of('inbound'):
            return self.env['account.journal']
        return journal

    @api.model
    def default_get(self, fields_list):
        """Main hook: the Pay dialog opens with the proof's journal already
        in place (a default is never overwritten by the computed one)."""
        res = super().default_get(fields_list)
        if 'journal_id' not in fields_list:
            return res
        try:
            ctx = self.env.context
            active_ids = ctx.get('active_ids') or []
            moves = self.env['account.move']
            if ctx.get('active_model') == 'account.move':
                moves = moves.browse(active_ids).exists()
            elif ctx.get('active_model') == 'account.move.line':
                moves = self.env['account.move.line'].browse(
                    active_ids).exists().move_id
            journal = self._proof_journal_for_moves(moves) if moves \
                else self.env['account.journal']
            if journal:
                res['journal_id'] = journal.id
        except Exception:
            _logger.exception(
                "accounting_so_invoice_bridge: could not preselect the "
                "payment-proof journal - the standard journal is kept.")
        return res

    @api.depends('available_journal_ids')
    def _compute_journal_id(self):
        """Backup hook for flows where the journal is computed instead of
        coming from the defaults."""
        super()._compute_journal_id()
        for wizard in self:
            try:
                journal = self._proof_journal_for_moves(
                    wizard.line_ids.move_id)
            except Exception:
                _logger.exception("payment-proof journal lookup failed")
                continue
            if journal and journal in wizard.available_journal_ids:
                wizard.journal_id = journal
