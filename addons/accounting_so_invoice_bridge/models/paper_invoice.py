"""Paper invoice numbers, void paper invoices and the invoice date chosen by
the salesperson.

* The paper invoice number is the existing **Reference** field
  (``cim_reference``, custom_invoice_management / _sale). One paper number
  belongs to ONE sale order (and its own invoices / credit notes) or to ONE
  void paper invoice, never two. Compared without spaces, dashes or case
  (``x_paper_ref_key``).
* A **void paper invoice** is a customer invoice without lines in its own
  journal ("Void Paper Invoices"), flagged ``x_is_void``. It never gets an
  INV number and never touches revenue, tax or customer balances. The
  salesperson voids it in one step (popup, sudo: salespeople only read
  invoices): it is created cancelled, numbered "VOID/<paper no>", and shows
  as "Void" in Accounting's Invoices list at once. Final.
* The salesperson enters the **Invoice Date** in the Create invoice(s)
  popup; it is written into the draft invoice(s). Accounting can still
  change it before confirming.
"""
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools import SQL
from odoo.tools.sql import column_exists, create_column

_logger = logging.getLogger(__name__)

VOID_PREFIX = 'VOID/'
# Fields Odoo itself writes on any record (chatter, activities, followers);
# allowed on void paper invoices, everything else goes through the buttons.
_VOID_FREE_FIELDS = ('message_', 'activity_', 'website_message')


def paper_key(value):
    """'csi 1559' / 'CSI-1559' / 'CSI1559' -> 'CSI1559' (False if empty).
    Same rule as the SQL used to fill existing rows (_fill_paper_key)."""
    key = re.sub(r'[^0-9A-Za-z]', '', value or '').upper()
    return key or False


def _fill_paper_key(cr, table):
    """Create + fill x_paper_ref_key in SQL on install/upgrade, so Odoo does
    not recompute it record by record over every existing order/move."""
    if column_exists(cr, table, 'x_paper_ref_key'):
        return
    create_column(cr, table, 'x_paper_ref_key', 'varchar')
    cr.execute(SQL(
        """UPDATE %s
              SET x_paper_ref_key = NULLIF(UPPER(REGEXP_REPLACE(
                      cim_reference, '[^0-9A-Za-z]', '', 'g')), '')
            WHERE cim_reference IS NOT NULL""", SQL.identifier(table)))


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    x_is_paper_void = fields.Boolean(
        string="Void Paper Invoices Journal", copy=False, readonly=True,
        help="Journal holding the void paper invoices. Created automatically; "
             "never used for real invoices.")


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_paper_ref_key = fields.Char(
        compute='_compute_x_paper_ref_key', store=True, index=True)

    def _auto_init(self):
        _fill_paper_key(self.env.cr, self._table)
        return super()._auto_init()

    @api.depends('cim_reference')
    def _compute_x_paper_ref_key(self):
        for order in self:
            order.x_paper_ref_key = paper_key(order.cim_reference)

    @api.constrains('cim_reference')
    def _check_paper_reference_unique(self):
        Move = self.env['account.move'].sudo()
        for order in self:
            key = paper_key(order.cim_reference)
            if not key:
                continue
            other = self.sudo().search([
                ('x_paper_ref_key', '=', key),
                ('company_id', '=', order.company_id.id),
                ('id', '!=', order.id),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    "Paper invoice number %(ref)s is already used on order "
                    "%(order)s. Each paper invoice number can be used once.",
                    ref=order.cim_reference, order=other.name))
            void = Move.search([
                ('x_is_void', '=', True),
                ('x_paper_ref_key', '=', key),
                ('company_id', '=', order.company_id.id),
            ], limit=1)
            if void:
                raise ValidationError(_(
                    "Paper invoice number %(ref)s was reported as VOID "
                    "(%(date)s). Use the next paper invoice.",
                    ref=order.cim_reference,
                    date=void.invoice_date or ''))

    def _check_paper_reference_set(self):
        missing = self.filtered(lambda o: not (o.cim_reference or '').strip())
        if missing:
            raise UserError(_(
                "Enter the paper invoice number in the Reference field of "
                "%(orders)s before creating the invoice.",
                orders=', '.join(missing.mapped('name'))))

    def _create_invoices(self, grouped=False, final=False, date=None):
        if not self.env.su:
            self._check_paper_reference_set()
        return super()._create_invoices(grouped=grouped, final=final, date=date)


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    x_invoice_date = fields.Date(
        string="Invoice Date", default=fields.Date.context_today,
        help="Date written on the paper invoice. Accounting receives the "
             "draft invoice with this date (they can still correct it).")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # Tell the salesperson right away, not after filling the popup.
        order_ids = res.get('sale_order_ids')
        if order_ids and not self.env.su:
            ids = []
            for cmd in order_ids:
                if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == 6:
                    ids += list(cmd[2])
                elif isinstance(cmd, int):
                    ids.append(cmd)
            if ids:
                self.env['sale.order'].browse(ids)._check_paper_reference_set()
        return res

    @api.constrains('x_invoice_date')
    def _check_x_invoice_date(self):
        for wizard in self:
            if wizard.x_invoice_date and \
                    wizard.x_invoice_date > fields.Date.context_today(wizard):
                raise ValidationError(_(
                    "The invoice date cannot be in the future."))

    def _create_invoices(self, sale_orders):
        if not self.env.su:
            sale_orders._check_paper_reference_set()
        if not self.x_invoice_date:
            raise UserError(_("Enter the Invoice Date."))
        if self.x_invoice_date > fields.Date.context_today(self):
            raise UserError(_("The invoice date cannot be in the future."))
        invoices = super()._create_invoices(sale_orders)
        drafts = invoices.filtered(lambda m: m.state == 'draft')
        if drafts:
            # Salespeople only read invoices: the invoice was created
            # through sudo by Odoo, the date is written the same way.
            drafts.sudo().write({'invoice_date': self.x_invoice_date})
        return invoices


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_paper_ref_key = fields.Char(
        compute='_compute_x_paper_ref_key', store=True, index=True)

    x_is_void = fields.Boolean(
        string="Void Paper Invoice", copy=False, readonly=True, index=True)
    x_void_state = fields.Selection([
        ('void', 'Void'),
    ], string="Void Status", copy=False, readonly=True)
    x_void_reason = fields.Text(
        string="Void Reason", copy=False, readonly=True, tracking=True)
    x_void_branch_id = fields.Many2one(
        'stock.warehouse', string="Void Branch", copy=False, readonly=True)

    status_in_payment = fields.Selection(selection_add=[('void', 'Void')])

    def _auto_init(self):
        _fill_paper_key(self.env.cr, self._table)
        return super()._auto_init()

    @api.depends('cim_reference')
    def _compute_x_paper_ref_key(self):
        for move in self:
            move.x_paper_ref_key = paper_key(move.cim_reference)

    @api.depends('x_is_void')
    def _compute_invoice_partner_display_info(self):
        # A void has no customer: show what it is instead of Odoo's
        # "#Created by: <user>" in the Customer column.
        super()._compute_invoice_partner_display_info()
        for move in self.filtered('x_is_void'):
            move.invoice_partner_display_name = _("Void paper invoice")

    @api.depends('x_is_void')
    def _compute_x_sale_type(self):
        # A void is neither a cash nor a credit sale (customer_credit_report
        # would call it "cash" because it has no credit payment term).
        super()._compute_x_sale_type()
        for move in self.filtered('x_is_void'):
            move.x_sale_type = False

    # ------------------------------------------------------------------
    # "Void" status in the invoice lists
    # ------------------------------------------------------------------
    @api.depends('x_is_void')
    def _compute_status_in_payment(self):
        super()._compute_status_in_payment()
        for move in self.filtered('x_is_void'):
            move.status_in_payment = 'void'

    def _search_status_in_payment(self, operator, value):
        if isinstance(value, bool):
            return super()._search_status_in_payment(operator, value)
        values = list(value) if isinstance(value, (list, tuple, set)) \
            else [value]
        others = [v for v in values if v != 'void']
        negative = operator in ('!=', 'not in')
        # Same meaning as the CASE in _field_to_sql: a void is only ever
        # "Void", never "Draft" or "Cancelled".
        rest = None
        if others:
            rest = super()._search_status_in_payment(
                'not in' if negative else 'in', others)
            rest = (expression.OR([rest, [('x_is_void', '=', True)]])
                    if negative else
                    expression.AND([rest, [('x_is_void', '=', False)]]))
        if 'void' in values:
            void = [('x_is_void', '=', not negative)]
            if rest is None:
                return void
            return (expression.AND if negative else expression.OR)([void, rest])
        return rest if rest is not None else []

    def _field_to_sql(self, alias, fname, query=None, flush=True):
        if fname == 'status_in_payment':
            return SQL(
                "CASE WHEN %s.x_is_void THEN 'void' ELSE %s END",
                SQL.identifier(alias),
                super()._field_to_sql(alias, fname, query=query, flush=flush))
        return super()._field_to_sql(alias, fname, query=query, flush=flush)

    # ------------------------------------------------------------------
    # Paper number rules
    # ------------------------------------------------------------------
    @api.constrains('cim_reference', 'x_is_void')
    def _check_paper_reference_void(self):
        Order = self.env['sale.order'].sudo()
        Move = self.sudo()
        for move in self:
            key = paper_key(move.cim_reference)
            if move.x_is_void:
                if not key:
                    raise ValidationError(_(
                        "Enter the paper invoice number of the void invoice."))
                domain_company = [('company_id', '=', move.company_id.id)]
                other_void = Move.search(domain_company + [
                    ('x_is_void', '=', True),
                    ('x_paper_ref_key', '=', key),
                    ('id', '!=', move.id),
                ], limit=1)
                if other_void:
                    raise ValidationError(_(
                        "Paper invoice number %(ref)s is already reported as "
                        "void.", ref=move.cim_reference))
                order = Order.search(domain_company + [
                    ('x_paper_ref_key', '=', key)], limit=1)
                if order:
                    raise ValidationError(_(
                        "Paper invoice number %(ref)s is used on order "
                        "%(order)s, so it cannot be void. If that paper was "
                        "really spoiled, Accounting first clears the "
                        "Reference on the order.",
                        ref=move.cim_reference, order=order.name))
                invoice = Move.search(domain_company + [
                    ('x_is_void', '=', False),
                    ('move_type', 'in', ('out_invoice', 'out_refund')),
                    ('x_paper_ref_key', '=', key),
                ], limit=1)
                if invoice:
                    raise ValidationError(_(
                        "Paper invoice number %(ref)s is used on invoice "
                        "%(inv)s, so it cannot be void.",
                        ref=move.cim_reference, inv=invoice.display_name))
            elif key and move.move_type in ('out_invoice', 'out_refund'):
                void = Move.search([
                    ('company_id', '=', move.company_id.id),
                    ('x_is_void', '=', True),
                    ('x_paper_ref_key', '=', key),
                ], limit=1)
                if void:
                    raise ValidationError(_(
                        "Paper invoice number %(ref)s was reported as VOID. "
                        "Use the next paper invoice.", ref=move.cim_reference))

    @api.constrains('journal_id', 'x_is_void')
    def _check_void_journal(self):
        for move in self:
            if bool(move.journal_id.x_is_paper_void) != bool(move.x_is_void):
                raise ValidationError(_(
                    "The journal \"%s\" is only for void paper invoices.",
                    move.journal_id.name) if move.journal_id.x_is_paper_void
                    else _("A void paper invoice must stay in the Void Paper "
                           "Invoices journal."))

    # ------------------------------------------------------------------
    # Void records are changed only through their buttons
    # ------------------------------------------------------------------
    def write(self, vals):
        if not self.env.su and any(self.mapped('x_is_void')):
            blocked = [f for f in vals if not f.startswith(_VOID_FREE_FIELDS)]
            if blocked:
                raise UserError(_("A void paper invoice is final and cannot "
                                  "be edited."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_void(self):
        if self.env.su:
            return
        if any(self.mapped('x_is_void')):
            raise UserError(_("A void paper invoice is final and cannot be "
                              "deleted."))

    def _post(self, soft=True):
        if self.filtered('x_is_void'):
            raise UserError(_("A void paper invoice cannot be confirmed."))
        return super()._post(soft=soft)

    def button_cancel(self):
        if not self.env.context.get('bridge_void_create') and \
                self.filtered('x_is_void'):
            raise UserError(_("A void paper invoice is already final."))
        return super().button_cancel()

    def button_draft(self):
        if self.filtered('x_is_void'):
            raise UserError(_("A void paper invoice is final."))
        return super().button_draft()

    # ------------------------------------------------------------------
    # Journal
    # ------------------------------------------------------------------
    @api.model
    def _bridge_void_journal(self, company):
        Journal = self.env['account.journal'].sudo()
        journal = Journal.search([
            ('x_is_paper_void', '=', True),
            ('company_id', '=', company.id),
        ], limit=1)
        if journal:
            return journal
        code = 'VOID'
        n = 1
        while Journal.search_count([('code', '=', code),
                                    ('company_id', '=', company.id)]):
            n += 1
            code = 'VOID%s' % n
        return Journal.create({
            'name': _('Void Paper Invoices'),
            'code': code,
            'type': 'sale',
            'company_id': company.id,
            'x_is_paper_void': True,
            'show_on_dashboard': False,
            'sequence': 99,
        })

    # ------------------------------------------------------------------
    # Salesperson: void a paper invoice (one step, final)
    # ------------------------------------------------------------------
    def action_bridge_report_void(self):
        """List header button (display="always", called on an empty or
        any selection): open the 'Void Paper Invoice' popup."""
        return self.env['paper.invoice.void.wizard']._open()

    @api.model
    def _bridge_create_void(self, company, number, date, branch, reason):
        """Create the void already final: cancelled, numbered VOID/<no>.
        Salespeople only read invoices, hence sudo (after the popup's
        checks); the paper number rules run as constraints."""
        move = self.sudo().with_company(company).create({
            'move_type': 'out_invoice',
            'company_id': company.id,
            'journal_id': self._bridge_void_journal(company).id,
            'x_is_void': True,
            'x_void_state': 'void',
            'cim_reference': number,
            'invoice_date': date,
            'invoice_user_id': self.env.user.id,
            'x_void_branch_id': branch.id,
            'x_void_reason': reason,
        })
        move.with_context(bridge_void_create=True).button_cancel()
        move.name = VOID_PREFIX + number
        move.message_post(body=_("Paper invoice %(ref)s voided by %(user)s. "
                                 "Reason: %(reason)s",
                                 ref=number, user=self.env.user.name,
                                 reason=reason))
        return move
