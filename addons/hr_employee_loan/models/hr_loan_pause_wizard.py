# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class HrLoanPauseWizard(models.TransientModel):
    _name = 'hr.loan.pause.wizard'
    _description = 'Pause Loan Deduction'

    loan_ids = fields.Many2many(
        'hr.loan', string='Loans',
        default=lambda self: self._default_loans())
    reason = fields.Char(string='Reason', required=True)

    def _default_loans(self):
        ctx = self.env.context
        if ctx.get('active_model') == 'hr.loan' and ctx.get('active_ids'):
            return [(6, 0, ctx['active_ids'])]
        return False

    def action_apply(self):
        self.ensure_one()
        self.env['hr.loan']._check_manager()
        loans = self.loan_ids.filtered(lambda l: l.state == 'running' and l.deduction_active)
        if not loans:
            raise UserError(_("There is no running loan with an active deduction to pause."))
        loans._pause_deduction(self.reason)
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}
