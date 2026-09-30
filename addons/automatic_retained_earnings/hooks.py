# -*- coding: utf-8 -*-
"""
Runs once, right after the module is installed.

For every existing company that does not already have a Retained Earnings
account configured, this:
  1. Creates ONE new Chart of Accounts entry - an equity account named
     "Retained Earnings" - if a suitable one does not already exist.
  2. Assigns it as the company's retained_earnings_account_id.
  3. Assigns a default closing journal (first Miscellaneous/General journal
     found) if none is set.

Everything else (tracking every income/expense account) needs no extra
setup - Odoo's own chart of accounts already does that; this module only
adds the missing "close the year into Retained Earnings" step.
"""
from odoo import api, SUPERUSER_ID


def post_init_hook(cr, registry=None):
    # Support both the Odoo <= 16 (cr, registry) and Odoo 17/18
    # (env) post_init_hook signatures.
    if registry is None and hasattr(cr, 'registry'):
        env = cr
    else:
        env = api.Environment(cr, SUPERUSER_ID, {})

    for company in env['res.company'].search([]):
        _ensure_retained_earnings_setup(env, company)


def _ensure_retained_earnings_setup(env, company):
    if not company.retained_earnings_account_id:
        account = _find_or_create_retained_earnings_account(env, company)
        company.retained_earnings_account_id = account.id

    if not company.closing_journal_id:
        journal_domain = [('type', '=', 'general')]
        if 'company_id' in env['account.journal']._fields:
            journal_domain.append(('company_id', '=', company.id))
        journal = env['account.journal'].search(journal_domain, limit=1)
        if journal:
            company.closing_journal_id = journal.id


def _find_or_create_retained_earnings_account(env, company):
    Account = env['account.account']
    company_field = 'company_ids' if 'company_ids' in Account._fields else (
        'company_id' if 'company_id' in Account._fields else None)

    base_domain = [('account_type', '=', 'equity'), ('deprecated', '=', False)]
    if company_field == 'company_ids':
        base_domain.append(('company_ids', 'in', company.id))
    elif company_field == 'company_id':
        base_domain.append(('company_id', '=', company.id))

    existing = Account.search(base_domain + [('name', 'ilike', 'Retained Earnings')], limit=1)
    if existing:
        return existing

    vals = {
        'code': _next_free_code(env, company, company_field),
        'name': 'Retained Earnings',
        'account_type': 'equity',
    }
    if company_field == 'company_ids':
        vals['company_ids'] = [(6, 0, [company.id])]
    elif company_field == 'company_id':
        vals['company_id'] = company.id

    return Account.create(vals)


def _next_free_code(env, company, company_field):
    """Pick an unused account code in a high, clearly system-reserved range
    (990001, 990002, ...) so it never collides with a localization's chart
    of accounts. The code can be renamed by the accountant afterwards."""
    Account = env['account.account']
    code_domain_base = []
    if company_field == 'company_ids':
        code_domain_base = [('company_ids', 'in', company.id)]
    elif company_field == 'company_id':
        code_domain_base = [('company_id', '=', company.id)]

    for i in range(1, 1000):
        code = '99%04d' % i
        if not Account.search_count(code_domain_base + [('code', '=', code)]):
            return code
    return '999999'
