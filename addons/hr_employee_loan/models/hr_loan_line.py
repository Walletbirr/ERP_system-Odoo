# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrLoanLine(models.Model):
    _name = 'hr.loan.line'
    _description = 'Loan Installment'
    _order = 'loan_id, sequence, id'
    _rec_name = 'loan_id'

    loan_id = fields.Many2one('hr.loan', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(
        'hr.employee', related='loan_id.employee_id', store=True, index=True)
    company_id = fields.Many2one(
        'res.company', related='loan_id.company_id', store=True, index=True)
    currency_id = fields.Many2one('res.currency', related='loan_id.currency_id', store=True)
    sequence = fields.Integer(string='#', default=1)
    due_date = fields.Date(string='Due Date', required=True)
    amount = fields.Monetary(currency_field='currency_id', required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('skipped', 'Skipped'),
        ('cancel', 'Cancelled'),
    ], default='pending', required=True, index=True)
    paid_date = fields.Date(string='Paid On')
    payment_reference = fields.Char(string='Payslip / Reference')
    note = fields.Char(string='Note')
    pause_log_id = fields.Many2one(
        'hr.loan.pause.log', string='Hold Period', ondelete='set null', copy=False,
        help="Hold period that caused this installment to be skipped.")
    skip_origin_id = fields.Many2one(
        'hr.loan.line', string='Added Because Of', ondelete='set null', copy=False,
        help="Skipped installment that this end-of-schedule installment replaces.")

    def write(self, vals):
        if 'due_date' in vals and any(l.state != 'pending' for l in self):
            raise UserError(_("Only pending installments can be rescheduled."))
        return super().write(vals)

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------
    def action_skip(self):
        """Skip this month: the installment is not deducted and an identical
        one is appended to the end of the schedule, so the employee still
        repays the full loan."""
        self.env['hr.loan']._check_manager()
        for line in self:
            line._do_skip()
        return True

    def _do_skip(self, note=None, pause_log=None, reference=None):
        """Skip one installment and append an identical one at the end.
        Used by the button (manager) and automatically by payroll."""
        self.ensure_one()
        loan = self.loan_id
        if self.state != 'pending' or loan.state != 'running':
            raise UserError(_("Only pending installments of a running loan can be skipped."))
        last = loan.line_ids.sorted('sequence')[-1]
        vals = {'state': 'skipped'}
        if note:
            vals['note'] = note
        if pause_log:
            vals['pause_log_id'] = pause_log.id
        if reference:
            vals['payment_reference'] = reference
        self.write(vals)
        self.sudo().create({
            'loan_id': loan.id,
            'sequence': last.sequence + 1,
            'due_date': last.due_date + relativedelta(months=1),
            'amount': self.amount,
            'skip_origin_id': self.id,
        })
        loan.message_post(body=_(
            "Installment #%(n)s (%(d)s) skipped%(note)s. An identical installment "
            "was added at the end of the schedule.",
            n=self.sequence, d=self.due_date,
            note=(": " + self.note) if self.note else ""))

    def _undo_skip(self):
        """Undo an automatic skip (payslip cancelled): the skipped installment
        is pending again and the one appended for it is removed."""
        for line in self.filtered(lambda l: l.state == 'skipped'):
            added = self.sudo().search([('skip_origin_id', '=', line.id)])
            if any(a.state != 'pending' for a in added):
                continue  # the appended installment was already used
            added.unlink()
            line.write({'state': 'pending', 'note': False,
                        'payment_reference': False, 'pause_log_id': False})
            line.loan_id.message_post(body=_(
                "Skip of installment #%s reverted (payslip cancelled).", line.sequence))
        return True

    def action_mark_paid(self):
        """Manual repayment (cash payment, or back-filling history). No
        journal entry is created - payroll / accounting handles that."""
        self.env['hr.loan']._check_manager()
        self._mark_paid()
        return True

    # ------------------------------------------------------------------
    # API for payroll
    # ------------------------------------------------------------------
    def _mark_paid(self, paid_date=None, reference=None):
        for line in self:
            if line.state != 'pending':
                raise UserError(_("Installment #%(n)s of %(loan)s is not pending.",
                                  n=line.sequence, loan=line.loan_id.name))
            line.write({
                'state': 'paid',
                'paid_date': paid_date or fields.Date.context_today(line),
                'payment_reference': reference or line.payment_reference,
            })
            loan = line.loan_id
            loan.message_post(body=_("Installment #%(n)s paid (%(amt)s)%(ref)s.",
                                     n=line.sequence, amt=line.amount,
                                     ref=(" - " + reference) if reference else ""))
            if not loan.line_ids.filtered(lambda l: l.state == 'pending'):
                loan.state = 'paid'
                loan.message_post(body=_("Loan fully repaid."))
        return True

    def _revert_paid(self):
        """Undo a payment (e.g. the payslip was cancelled)."""
        for line in self:
            if line.state != 'paid':
                continue
            line.write({'state': 'pending', 'paid_date': False, 'payment_reference': False})
            if line.loan_id.state == 'paid':
                line.loan_id.state = 'running'
            line.loan_id.message_post(body=_("Payment of installment #%s reverted.", line.sequence))
        return True
