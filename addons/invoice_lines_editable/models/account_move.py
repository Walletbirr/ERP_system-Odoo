from contextlib import contextmanager

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import trace
from .arch_patch import patch_move_form_arch

# Context keys that stop the standard recalculation and the automatic
# Service Charge balancing of custom_invoice_management (a harmless unknown
# key when that module is not installed).
MANUAL_CONTEXT = {
    'skip_invoice_sync': True,
    'cim_skip_auto_balance': True,
}


class AccountMove(models.Model):
    _inherit = 'account.move'

    manual_journal_items = fields.Boolean(
        string='Manual Journal Items',
        copy=False,
        help="When ticked, Odoo stops recalculating the tax, receivable/payable "
             "and rounding lines of this invoice from the Invoice Lines when it "
             "is saved or posted. The journal items are kept exactly as you "
             "typed them. The entry must still be balanced to be saved/posted. "
             "Untick it to go back to the automatic calculation.",
    )

    # ------------------------------------------------------------------
    # View: unlock Debit/Credit, show the switch
    # ------------------------------------------------------------------
    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            patch_move_form_arch(arch)
        return arch, view

    # ------------------------------------------------------------------
    # Backend: do not recompute the dynamic lines in manual mode
    # ------------------------------------------------------------------
    @contextmanager
    def _sync_dynamic_lines(self, container):
        records = container.get('records') or self.browse()
        if records and all(records.mapped('manual_journal_items')):
            yield
            return
        with super()._sync_dynamic_lines(container):
            yield

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('manual_journal_items') for vals in vals_list):
            if all(vals.get('manual_journal_items') for vals in vals_list):
                self = self.with_context(**MANUAL_CONTEXT)
            else:
                moves = self.browse()
                for vals in vals_list:
                    moves |= self.with_context(
                        **(MANUAL_CONTEXT if vals.get('manual_journal_items') else {})
                    ).create([vals])
                return moves
        return super().create(vals_list)

    def write(self, vals):
        # Leaving manual mode: let the standard recalculation run.
        if 'manual_journal_items' in vals and not vals['manual_journal_items']:
            return super().write(vals)
        # The switch may be ticked in the very same save that edits the
        # lines, before the stored value is updated: honour it right away.
        manual = self if vals.get('manual_journal_items') else self.filtered('manual_journal_items')
        if not manual:
            return super().write(vals)
        res = super(AccountMove, manual.with_context(**MANUAL_CONTEXT)).write(vals)
        rest = self - manual
        if rest:
            res = super(AccountMove, rest).write(vals)
        return res

    # ------------------------------------------------------------------
    # A clear message instead of "The entry is not balanced."
    # ------------------------------------------------------------------
    @contextmanager
    def _check_balanced(self, container):
        try:
            with super()._check_balanced(container):
                yield
        except UserError:
            for move in (container.get('records') or self.browse()).filtered('manual_journal_items'):
                diff = move.currency_id.round(sum(move.line_ids.mapped('balance')))
                if move.company_currency_id.is_zero(diff):
                    continue
                trace.log_failure(self.env, move)
                raise UserError(_(
                    "The journal items of this invoice are not balanced: debits "
                    "and credits differ by %(diff)s. Check that the debit and "
                    "credit amounts add up.",
                    diff=move.company_currency_id.format(abs(diff)),
                ))
            raise
