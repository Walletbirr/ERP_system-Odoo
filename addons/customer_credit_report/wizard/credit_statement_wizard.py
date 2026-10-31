from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CustomerCreditStatementWizard(models.TransientModel):
    _name = 'customer.credit.statement.wizard'
    _description = 'Customer Credit Statement'

    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True,
        domain="[('is_company', '=', True)]")
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company)
    period = fields.Selection([
        ('all', 'Since the first credit sale'),
        ('this_year', 'This year'),
        ('custom', 'Choose dates'),
    ], default='all', required=True)
    date_from = fields.Date(string='From')
    date_to = fields.Date(string='To', required=True,
                          default=fields.Date.context_today)

    @api.onchange('period')
    def _onchange_period(self):
        today = fields.Date.context_today(self)
        if self.period == 'this_year':
            self.date_from = today.replace(month=1, day=1)
            self.date_to = today
        elif self.period == 'all':
            self.date_from = False
            self.date_to = today

    def _dates(self):
        self.ensure_one()
        if self.period == 'custom' and not self.date_from:
            raise UserError(_('Choose the start date of the statement.'))
        if self.date_from and self.date_from > self.date_to:
            raise UserError(_('The start date is after the end date.'))
        return (self.date_from if self.period != 'all' else False,
                self.date_to)

    def _report_values(self):
        self.ensure_one()
        date_from, date_to = self._dates()
        return self.env['customer.credit.statement']._get_statement(
            self.partner_id.commercial_partner_id, self.company_id,
            date_from=date_from, date_to=date_to)

    def action_print(self):
        self._dates()
        return self.env.ref(
            'customer_credit_report.action_report_credit_statement'
        ).report_action(self)

    def action_show(self):
        self._dates()
        action = self.env.ref(
            'customer_credit_report.action_report_credit_statement_html'
        ).report_action(self)
        return action


class ReportCreditStatement(models.AbstractModel):
    _name = 'report.customer_credit_report.report_credit_statement'
    _description = 'Customer Credit Statement Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['customer.credit.statement.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'customer.credit.statement.wizard',
            'docs': wizards,
            'statements': [w._report_values() for w in wizards],
        }
