# -*- coding: utf-8 -*-
from odoo import api, fields, models

HISTORY_LIMIT = 30


class PaymentPurposeHistory(models.Model):
    _name = 'payment.purpose.history'
    _description = 'Payment Purpose History'
    _order = 'last_used desc, id desc'

    name = fields.Char(string="Purpose", required=True)
    user_id = fields.Many2one(
        'res.users', string="User", required=True, index=True,
        default=lambda self: self.env.uid, ondelete='cascade')
    last_used = fields.Datetime(default=fields.Datetime.now)

    @api.model
    def remember(self, text):
        """ Add (or move to the top) a purpose in the current user's history. """
        text = (text or '').strip()
        if not text:
            return
        history = self.sudo()
        domain = [('user_id', '=', self.env.uid)]
        record = history.search(domain + [('name', '=', text)], limit=1)
        if record:
            record.last_used = fields.Datetime.now()
        else:
            history.create({'name': text, 'user_id': self.env.uid})
        history.search(domain, offset=HISTORY_LIMIT).unlink()

    @api.model
    def clear_all(self):
        self.sudo().search([('user_id', '=', self.env.uid)]).unlink()
        return True
