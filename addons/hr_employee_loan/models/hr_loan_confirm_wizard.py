# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrLoanConfirmWizard(models.TransientModel):
    _name = 'hr.loan.confirm.wizard'
    _description = 'Confirm Loan - Journal Entry Preview'

    loan_id = fields.Many2one('hr.loan', required=True, readonly=True, ondelete='cascade')
    currency_id = fields.Many2one(related='loan_id.currency_id')
    employee_id = fields.Many2one(related='loan_id.employee_id')
    date = fields.Date(related='loan_id.date')
    loan_amount = fields.Monetary(related='loan_id.loan_amount', currency_field='currency_id')
    installment_amount = fields.Monetary(
        related='loan_id.installment_amount', currency_field='currency_id')
    installment_count = fields.Integer(related='loan_id.installment_count')
    first_deduction_date = fields.Date(related='loan_id.first_deduction_date')
    last_deduction_date = fields.Date(compute='_compute_last_deduction_date')
    create_entry = fields.Boolean(related='loan_id.create_disbursement_entry')
    journal_id = fields.Many2one(related='loan_id.journal_id')
    line_ids = fields.One2many('hr.loan.confirm.wizard.line', 'wizard_id', string='Journal Items')

    @api.depends('first_deduction_date', 'installment_count')
    def _compute_last_deduction_date(self):
        for wiz in self:
            if wiz.first_deduction_date and wiz.installment_count:
                wiz.last_deduction_date = wiz.first_deduction_date + relativedelta(
                    months=wiz.installment_count - 1)
            else:
                wiz.last_deduction_date = False

    def action_confirm_post(self):
        self.ensure_one()
        if self.loan_id.state != 'draft':
            raise UserError(_("This loan is no longer in Draft."))
        self.loan_id.action_confirm()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}


class HrLoanConfirmWizardLine(models.TransientModel):
    _name = 'hr.loan.confirm.wizard.line'
    _description = 'Confirm Loan - Journal Item Preview'

    wizard_id = fields.Many2one('hr.loan.confirm.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    account_id = fields.Many2one('account.account', string='Account')
    partner_id = fields.Many2one('res.partner', string='Partner')
    name = fields.Char(string='Description')
    debit = fields.Monetary(currency_field='currency_id')
    credit = fields.Monetary(currency_field='currency_id')
