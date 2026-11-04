from odoo import _, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # The customer's own account in the chart of accounts (named after
    # them) that carries what they owed before Odoo. Setting it also makes
    # it their Account Receivable, so new credit sales add to it and
    # payments deduct from it. What was on it before their first credit
    # sale in Odoo is their Previous Balance (see credit_line.py).
    x_credit_account_id = fields.Many2one(
        'account.account', company_dependent=True, string='Credit Account',
        domain="[('account_type', '=', 'asset_receivable'), "
               "('deprecated', '=', False)]",
        ondelete='restrict',
        help="This customer's own account (named after them) holding what "
             "they owed before Odoo. It also becomes their Account "
             "Receivable. Its balance before their first credit sale in "
             "Odoo is shown as their Previous Balance.")
    x_credit_previous = fields.Monetary(
        string='Previous Balance', compute='_compute_x_credit_position',
        currency_field='x_credit_currency_id',
        help='What the customer still owes from before their first credit '
             'sale in Odoo.')

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
            partner.x_credit_previous = pos['previous']
            partner.x_credit_invoice_count = pos['invoice_count']
            partner.x_credit_open_count = pos['open_invoice_count']
            partner.x_total_invoiced = pos['amount_total']
            partner.x_credit_amount_paid = pos['amount_paid']
            partner.x_remaining_balance = pos['remaining']

    # ------------------------------------------------------------------
    # Credit Account
    # ------------------------------------------------------------------
    def write(self, vals):
        account_id = vals.get('x_credit_account_id')
        if account_id:
            vals = dict(vals, property_account_receivable_id=account_id)
        res = super().write(vals)
        if 'x_credit_account_id' in vals:
            self._check_credit_account()
        return res

    def _check_credit_account(self):
        for partner in self:
            account = partner.x_credit_account_id
            if not account:
                continue
            if account.account_type != 'asset_receivable' \
                    or not account.reconcile:
                raise ValidationError(_(
                    "%(account)s cannot be a Credit Account: in the Chart "
                    "of Accounts set its Type to \"Receivable\" and tick "
                    "\"Allow Reconciliation\".",
                    account=account.display_name))
            if partner.parent_id:
                raise ValidationError(_(
                    "Set the Credit Account on the company %s, not on one "
                    "of its contacts.",
                    partner.commercial_partner_id.display_name))
            others = self.sudo().search([
                ('id', '!=', partner.id),
                ('x_credit_account_id', '=', account.id)], limit=1)
            if others:
                raise ValidationError(_(
                    "%(account)s is already the Credit Account of "
                    "%(other)s. Each customer needs their own account.",
                    account=account.display_name,
                    other=others.display_name))

    def action_view_credit_account(self):
        """Journal items of the customer's own Credit Account."""
        partner = self._credit_partner()
        account = partner.x_credit_account_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credit Account — %s', partner.display_name),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('account_id', '=', account.id),
                       ('parent_state', '=', 'posted')],
            'context': {'search_default_group_by_move': 0},
        }

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
