from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'sale.void.mixin']

    x_void_status = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Posted'),
         ('cancel', 'Cancelled'), ('void', 'Void')],
        string='Status', compute='_compute_x_void_status')

    @api.depends('x_is_voided', 'state')
    def _compute_x_void_status(self):
        for move in self:
            move.x_void_status = (
                'void' if move.x_is_voided
                else (move.state if move.state in
                      ('draft', 'posted', 'cancel') else False))

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type in ('list', 'tree'):
            self._void_patch_list_status(
                arch,
                success="x_void_status == 'posted'",
                info="x_void_status == 'draft'")
        return arch, view

    x_void_order_id = fields.Many2one(
        'sale.order', string='Voided With Order', copy=False, readonly=True)

    def button_draft(self):
        if (not self.env.context.get('sale_order_void')
                and any(m.x_is_voided for m in self)):
            raise UserError(_(
                "A voided document cannot be set back to draft."))
        return super().button_draft()
