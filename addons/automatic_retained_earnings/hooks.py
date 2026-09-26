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

    _fix_menu_placement(env)


def _fix_menu_placement(env):
    """Nest our two menu items inside the Accounting app's real
    Configuration / Accounting submenus instead of hard-coding a guessed
    external id (that's what broke install the first time). Looked up by
    name anywhere under the Accounting app root (not just direct children,
    in case a kit nests things one level deeper), preferring the shallowest
    match. Runs on every install AND upgrade, so it keeps re-applying even
    though the XML always re-parents to the app root first.
    """
    Menu = env['ir.ui.menu'].sudo()
    finance_root = env.ref('account.menu_finance', raise_if_not_found=False)
    if not finance_root:
        return

    setup_menu = env.ref(
        'automatic_retained_earnings.menu_retained_earnings_config',
        raise_if_not_found=False)
    closing_menu = env.ref(
        'automatic_retained_earnings.menu_account_fiscalyear_closing',
        raise_if_not_found=False)

    config_menu = _find_submenu(Menu, finance_root, 'Configuration')
    accounting_menu = _find_submenu(Menu, finance_root, 'Accounting')

    if config_menu and setup_menu:
        setup_menu.write({'parent_id': config_menu.id, 'sequence': 99})
    if accounting_menu and closing_menu:
        closing_menu.write({'parent_id': accounting_menu.id, 'sequence': 99})
    # If either submenu isn't found (unusual sidebar layout), the items
    # simply stay where the XML puts them - directly under the Accounting
    # app root - which always works, just one level shallower.

    Menu.clear_caches()


def _find_submenu(Menu, root, label):
    """Find the menu named `label` living anywhere under `root`, preferring
    the one closest to root. Case-insensitive / whitespace-tolerant since
    exact text can vary slightly between localizations or accounting kits.
    """
    candidates = Menu.search([
        ('id', 'child_of', root.id),
        ('id', '!=', root.id),
        ('name', '=ilike', label.strip()),
    ])
    if not candidates:
        return Menu.browse()
    if len(candidates) == 1:
        return candidates

    def _depth(menu):
        depth, current, seen = 0, menu, set()
        while current.parent_id and current.id != root.id and current.id not in seen:
            seen.add(current.id)
            current = current.parent_id
            depth += 1
        return depth

    return Menu.browse(min(candidates, key=_depth).id)


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
