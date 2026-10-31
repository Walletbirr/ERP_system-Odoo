from odoo import fields, models, tools


class CustomerCreditSettlement(models.Model):
    """Payment settlement history: every amount matched to a credit
    invoice (normally a customer payment registered with the invoice's Pay
    button; also credit notes and other matched entries)."""
    _name = 'customer.credit.settlement'
    _description = 'Customer Credit Settlement'
    _auto = False
    _rec_name = 'payment_move_id'
    _order = 'date desc, id desc'

    invoice_id = fields.Many2one('account.move', string='Invoice',
                                 readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer',
                                 readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson',
                              readonly=True)
    date = fields.Date(string='Payment Date', readonly=True)
    amount = fields.Monetary(string='Amount Settled', readonly=True)
    payment_move_id = fields.Many2one('account.move', string='Entry',
                                      readonly=True)
    payment_id = fields.Many2one('account.payment', string='Payment',
                                 readonly=True)
    journal_id = fields.Many2one('account.journal', string='Bank / Journal',
                                 readonly=True)
    reference = fields.Char(readonly=True)
    kind = fields.Selection([('payment', 'Payment'),
                             ('credit_note', 'Credit Note'),
                             ('other', 'Other Entry')],
                            readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    apr.id                         AS id,
                    inv.id                         AS invoice_id,
                    inv.commercial_partner_id      AS partner_id,
                    inv.company_id                 AS company_id,
                    rc.currency_id                 AS currency_id,
                    inv.invoice_user_id            AS user_id,
                    cl.date                        AS date,
                    apr.amount                     AS amount,
                    cm.id                          AS payment_move_id,
                    pay.id                         AS payment_id,
                    cm.journal_id                  AS journal_id,
                    COALESCE(NULLIF(pay.memo, ''), cm.ref, cm.name)
                                                   AS reference,
                    CASE WHEN pay.id IS NOT NULL THEN 'payment'
                         WHEN cm.move_type = 'out_refund' THEN 'credit_note'
                         ELSE 'other' END          AS kind
                FROM account_partial_reconcile apr
                JOIN account_move_line dl ON dl.id = apr.debit_move_id
                JOIN account_move inv ON inv.id = dl.move_id
                JOIN account_move_line cl ON cl.id = apr.credit_move_id
                JOIN account_move cm ON cm.id = cl.move_id
                JOIN res_company rc ON rc.id = inv.company_id
                LEFT JOIN account_payment pay ON pay.move_id = cm.id
                WHERE inv.move_type = 'out_invoice'
                  AND inv.state = 'posted'
                  AND inv.x_sale_type = 'credit'
                  AND cm.state = 'posted'
            )
        """)

    def action_open_entry(self):
        self.ensure_one()
        if self.payment_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'res_id': self.payment_id.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.payment_move_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
