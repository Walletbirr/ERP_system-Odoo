from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Live credit position (company level customer, current company).
    x_credit_total = fields.Monetary(
        string='Total Credit', compute='_compute_x_credit_position',
        currency_field='x_credit_currency_id',
        help='Everything invoiced to this customer on credit (credit notes '
             'deducted).')
    x_credit_paid = fields.Monetary(
        string='Credit Paid', compute='_compute_x_credit_position',
        currency_field='x_credit_currency_id')
    x_credit_remaining = fields.Monetary(
        string='Credit Remaining', compute='_compute_x_credit_position',
        currency_field='x_credit_currency_id',
        help='Unpaid part of posted credit invoices.')
    x_credit_overdue = fields.Monetary(
        string='Credit Overdue', compute='_compute_x_credit_position',
        currency_field='x_credit_currency_id')
    x_credit_invoice_count = fields.Integer(
        string='Credit Invoices', compute='_compute_x_credit_position')
    x_credit_open_count = fields.Integer(
        string='Open Credit Invoices', compute='_compute_x_credit_position')
    x_credit_currency_id = fields.Many2one(
        'res.currency', compute='_compute_x_credit_position')

    # Kept for the management dashboard (finance.customer_credit), which
    # reads these names. They now come from the credit engine.
    x_total_invoiced = fields.Monetary(
        string='Total Invoiced on Credit', compute='_compute_x_credit_position',
        currency_field='x_credit_currency_id')
    x_credit_amount_paid = fields.Monetary(
        string='Amount Paid', compute='_compute_x_credit_position',
        currency_field='x_credit_currency_id')
    x_remaining_balance = fields.Monetary(
        string='Remaining Balance', compute='_compute_x_credit_position',
        currency_field='x_credit_currency_id')

    def _compute_x_credit_position(self):
        Summary = self.env['customer.credit.summary'].sudo()
        company = self.env.company
        for partner in self:
            pos = (Summary._position(partner, company) if partner.id
                   else Summary._empty_position())
            partner.x_credit_currency_id = company.currency_id
            partner.x_credit_total = pos['amount_total']
            partner.x_credit_paid = pos['amount_paid']
            partner.x_credit_remaining = pos['remaining']
            partner.x_credit_overdue = pos['overdue']
            partner.x_credit_invoice_count = pos['invoice_count']
            partner.x_credit_open_count = pos['open_invoice_count']
            partner.x_total_invoiced = pos['amount_total']
            partner.x_credit_amount_paid = pos['amount_paid']
            partner.x_remaining_balance = pos['remaining']

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _credit_partner(self):
        self.ensure_one()
        return self.commercial_partner_id

    def action_view_credit_lines(self):
        partner = self._credit_partner()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'customer_credit_report.action_customer_credit_line')
        action['name'] = _('Credit Invoices — %s', partner.display_name)
        action['domain'] = [('partner_id', '=', partner.id)]
        action['context'] = {'search_default_open': 1}
        return action

    def action_view_credit_settlements(self):
        partner = self._credit_partner()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'customer_credit_report.action_customer_credit_settlement')
        action['name'] = _('Payment Settlements — %s', partner.display_name)
        action['domain'] = [('partner_id', '=', partner.id)]
        action['context'] = {}
        return action

    def action_open_credit_statement(self):
        partner = self._credit_partner()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'customer_credit_report.action_credit_statement_wizard')
        action['context'] = {'default_partner_id': partner.id}
        return action

    def action_view_credit_summary(self):
        partner = self._credit_partner()
        summary = self.env['customer.credit.summary'].search([
            ('partner_id', '=', partner.id),
            ('company_id', '=', self.env.company.id)], limit=1)
        if not summary:
            return self.action_view_credit_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Credit'),
            'res_model': 'customer.credit.summary',
            'res_id': summary.id,
            'view_mode': 'form',
            'views': [(self.env.ref(
                'customer_credit_report.view_customer_credit_summary_form').id,
                'form')],
        }
