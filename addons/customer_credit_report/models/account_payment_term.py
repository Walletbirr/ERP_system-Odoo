from odoo import fields, models


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    x_is_credit = fields.Boolean(
        string='Credit Sale',
        help="Ticked: a sale on this term is a Credit sale. The customer "
             "pays later, the High-Level Manager approves the sale before "
             "it is confirmed (Credit Sales Report) and the unpaid part of "
             "the invoice is followed in Sales > Reporting > Customer "
             "Credit. The term's days give the invoice due date (used for "
             "overdue and ageing).\n"
             "Not ticked (or no term): a Cash sale.")
