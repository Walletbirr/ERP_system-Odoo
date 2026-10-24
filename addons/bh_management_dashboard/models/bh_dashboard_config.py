# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BhDashboardConfig(models.Model):
    """Which ledger accounts feed the Finance cards of the Executive
    Dashboard (Accounts Receivable, Accounts Payable, Cash at Bank).

    One record per company, opened from Executive Dashboard >
    Configuration > Finance Accounts. A list left EMPTY means "not
    configured": that card keeps its original behaviour (all receivable
    accounts / all payable accounts / all Bank & Cash journals).
    """
    _name = 'bh.dashboard.config'
    _description = 'BH Executive Dashboard - Finance Accounts'

    name = fields.Char(default='Finance Dashboard Settings', required=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company, ondelete='cascade')

    receivable_account_ids = fields.Many2many(
        'account.account', 'bh_dash_cfg_receivable_rel', 'config_id', 'account_id',
        string='Accounts Receivable Accounts',
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        help="Only these accounts are counted in the Accounts Receivable "
             "card. Leave empty to use every Receivable-type account.")
    payable_account_ids = fields.Many2many(
        'account.account', 'bh_dash_cfg_payable_rel', 'config_id', 'account_id',
        string='Accounts Payable Accounts',
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        help="Only these accounts are counted in the Accounts Payable "
             "card. Leave empty to use every Payable-type account.")
    cash_account_ids = fields.Many2many(
        'account.account', 'bh_dash_cfg_cash_rel', 'config_id', 'account_id',
        string='Cash at Bank Accounts',
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        help="Only these accounts are listed and summed in the Cash at "
             "Bank card. Leave empty to use the default account of every "
             "Bank and Cash journal.")

    # ---- Credit / Deposit break-down accounts --------------------------
    credit_customer_account_ids = fields.Many2many(
        'account.account', 'bh_dash_cfg_credit_cust_rel', 'config_id', 'account_id',
        string='Credit - Customer Accounts',
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        help="Accounts shown under 'From Customers' in the Credit break-down.")
    credit_staff_account_ids = fields.Many2many(
        'account.account', 'bh_dash_cfg_credit_staff_rel', 'config_id', 'account_id',
        string='Credit - Staff Accounts',
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        help="Accounts shown under 'From Staff' in the Credit break-down.")
    deposit_customer_account_ids = fields.Many2many(
        'account.account', 'bh_dash_cfg_deposit_cust_rel', 'config_id', 'account_id',
        string='Deposit - Customer Accounts',
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        help="Accounts shown under 'From Customers' in the Deposit break-down.")
    deposit_owner_account_ids = fields.Many2many(
        'account.account', 'bh_dash_cfg_deposit_owner_rel', 'config_id', 'account_id',
        string='Deposit - Owner Accounts',
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        help="Owner deposits are taken from the balance of these accounts "
             "and added to the Deposit total.")

    # ---- Company tab (Operations > Company > Finance) --------------------
    loan_account_ids = fields.Many2many(
        'account.account', 'bh_dash_cfg_loan_rel', 'config_id', 'account_id',
        string='Loan - Employee Accounts',
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        help="Employee loans. Debits on these accounts are money lent, "
             "credits are settlements. One line per person: the contact on "
             "the entry, or the account itself when there is none.")
    owner_account_ids = fields.Many2many(
        'account.account', 'bh_dash_cfg_owner_rel', 'config_id', 'account_id',
        string='Owner Account (Withdrawal & Fund)',
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        help="The account the accountant uses for BOTH owner operations. "
             "Withdrawal = Debit on this account (Credit Bank). "
             "Fund = Credit on this account (Debit Bank). The mobile app "
             "tracks the two separately, per owner.")

    _sql_constraints = [
        ('company_unique', 'unique(company_id)',
         'There can be only one Finance Accounts configuration per company.'),
    ]

    @api.constrains('receivable_account_ids', 'payable_account_ids')
    def _check_receivable_payable_overlap(self):
        for cfg in self:
            both = cfg.receivable_account_ids & cfg.payable_account_ids
            if both:
                raise ValidationError(_(
                    "An account cannot be both Receivable and Payable: %s",
                    ', '.join(both.mapped('display_name'))))

    @api.constrains('credit_customer_account_ids', 'credit_staff_account_ids')
    def _check_credit_overlap(self):
        for cfg in self:
            both = cfg.credit_customer_account_ids & cfg.credit_staff_account_ids
            if both:
                raise ValidationError(_(
                    "An account cannot be both a Customer and a Staff Credit "
                    "account: %s", ', '.join(both.mapped('display_name'))))

    @api.constrains('deposit_customer_account_ids', 'deposit_owner_account_ids')
    def _check_deposit_overlap(self):
        for cfg in self:
            both = cfg.deposit_customer_account_ids & cfg.deposit_owner_account_ids
            if both:
                raise ValidationError(_(
                    "An account cannot be both a Customer and an Owner Deposit "
                    "account: %s", ', '.join(both.mapped('display_name'))))

    def action_suggest_breakdown_accounts(self):
        """Pre-fill the four Credit / Deposit lists from the chart of
        accounts. ADDS to what is already selected, never removes.

        Rules (BINGET chart of accounts):
          * Credit - Staff       : name contains "STAFF" / "STAF"
          * Credit - Customer    : code starts with 1210-  (trade receivables)
          * Deposit - Customer   : code starts with 2100-  and name starts
                                   with "Customer"
          * Deposit - Owner      : "Payable to the owner" (2000-01)
        Review the result - people whose account name doesn't say STAFF
        (e.g. "MILION MEBIRE") must be added by hand.
        """
        self.ensure_one()
        accounts = self.env['account.account'].sudo().with_company(
            self.company_id).search([('deprecated', '=', False)])

        def pick(fn):
            return accounts.filtered(lambda a: fn((a.code or '').strip(),
                                                  (a.name or '').strip()))

        staff = pick(lambda c, n: re.search(r'\bstaf', n, re.I))
        customer = pick(lambda c, n: c.startswith('1210-')) - staff
        dep_customer = pick(lambda c, n: c.startswith('2100-')
                            and n.lower().startswith('customer'))
        owner = pick(lambda c, n: 'payable to the owner' in n.lower()
                     or c == '2000-01')
        self.write({
            'credit_staff_account_ids': [(4, i) for i in staff.ids],
            'credit_customer_account_ids': [(4, i) for i in customer.ids],
            'deposit_customer_account_ids': [(4, i) for i in (dep_customer - owner).ids],
            'deposit_owner_account_ids': [(4, i) for i in owner.ids],
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Accounts suggested"),
                'message': _("Staff: %(s)s, Customer credit: %(c)s, Customer deposit: %(d)s, "
                             "Owner: %(o)s. Please review the lists.",
                             s=len(staff), c=len(customer),
                             d=len(dep_customer - owner), o=len(owner)),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    @api.model
    def get_config(self):
        """The configuration record of the current company (created on
        first use)."""
        company = self.env.company
        config = self.sudo().search([('company_id', '=', company.id)], limit=1)
        if not config:
            config = self.sudo().create({'company_id': company.id})
        return config

    @api.model
    def action_open_config(self):
        """Used by the Configuration > Finance Accounts menu: open the
        current company's record directly in form view."""
        config = self.get_config()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Finance Accounts'),
            'res_model': self._name,
            'res_id': config.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }