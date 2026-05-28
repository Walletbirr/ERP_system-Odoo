# from odoo import models, fields
# from odoo.exceptions import ValidationError


# class AccountPayment(models.Model):
#     _inherit = 'account.payment'

#     def action_post(self):
#         res = super().action_post()

#         for payment in self:

#             # Only vendor payments
#             if payment.payment_type != 'outbound':
#                 continue

#             # Find linked bills
#             bills = payment.reconciled_bill_ids.filtered(
#                 lambda m: m.move_type == 'in_invoice'
#             )

#             for bill in bills:

#                 lc = bill.lc_id

#                 if not lc:
#                     continue

#                 if lc.state not in ('open', 'utilized'):
#                     raise ValidationError(
#                         "LC must be Open or Utilized."
#                     )

#                 amount = payment.amount

#                 if amount > lc.remaining_amount:
#                     raise ValidationError(
#                         "Payment exceeds LC remaining amount."
#                     )

#                 payable_line = bill.line_ids.filtered(
#                     lambda l: l.account_id.account_type == 'liability_payable'
#                 )

#                 if not payable_line:
#                     raise ValidationError(
#                         "No payable account found on bill."
#                     )

#                 payable_account = payable_line[0].account_id

#                 move = self.env['account.move'].create({
#                     'move_type': 'entry',
#                     'journal_id': lc.bank_journal_id.id,
#                     'line_ids': [

#                         (0, 0, {
#                             'name': f'LC Payment: {lc.name}',
#                             'account_id': payable_account.id,
#                             'debit': amount,
#                             'credit': 0.0,
#                         }),

#                         (0, 0, {
#                             'name': f'LC Payment: {lc.name}',
#                             'account_id': lc.margin_account_id.id,
#                             'debit': 0.0,
#                             'credit': amount,
#                         }),

#                     ]
#                 })

#                 move.action_post()

#         return res