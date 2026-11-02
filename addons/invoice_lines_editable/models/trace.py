"""Tiny per-transaction trace of who changed which journal item.

Only used on invoices in Manual Journal Items mode. It records, for each
create / write / unlink of a journal item, the amounts and the non-core
modules found in the Python call stack, so that an "entry is not balanced"
error can say exactly which module altered the amounts.
"""
import logging
import re
import traceback

_logger = logging.getLogger(__name__)

_NOISE = {'base', 'web', 'account', 'mail', 'invoice_lines_editable', 'bus',
          'portal', 'analytic', 'product', 'uom', 'sale', 'sale_stock', 'stock'}
_ADDON_RE = re.compile(r'[/\\](?:odoo[/\\])?addons[/\\]([A-Za-z0-9_]+)[/\\]')
_KEYS = ('debit', 'credit', 'balance', 'amount_currency', 'account_id',
         'display_type', 'price_unit', 'quantity', 'tax_ids')


def _modules():
    found = []
    for frame in traceback.extract_stack()[:-2]:
        match = _ADDON_RE.search(frame.filename)
        name = match.group(1) if match else None
        if not name:
            # custom addons usually live outside an "addons" folder: use the
            # folder that contains models/
            m2 = re.search(r'[/\\]([A-Za-z0-9_]+)[/\\]models[/\\]', frame.filename)
            name = m2.group(1) if m2 else None
        if name and name not in _NOISE and name not in found:
            found.append(name)
    return found


def record(env, op, ids, vals=None):
    store = env.cr.cache.setdefault('ile_trace', [])
    short = {k: v for k, v in (vals or {}).items() if k in _KEYS}
    entry = '%s %s %s [%s]' % (op, list(ids)[:6], short, ', '.join(_modules()) or 'core only')
    store.append(entry)
    del store[:-40]
    _logger.info('ILE-TRACE %s', entry)


def tail(env, count=10):
    return env.cr.cache.get('ile_trace', [])[-count:]


def log_failure(env, move):
    """Write the stored lines and the last changes to the server log."""
    lines = '; '.join(
        '#%s %s %s d=%s c=%s' % (l.id, l.display_type or '-', l.account_id.code or '-',
                                 l.debit, l.credit)
        for l in move.line_ids)
    _logger.warning('ILE unbalanced move %s: %s | changes: %s',
                    move.id, lines, ' || '.join(tail(env)))
