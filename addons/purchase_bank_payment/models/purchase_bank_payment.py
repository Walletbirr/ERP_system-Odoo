from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class PurchaseBankPayment(models.Model):
    """A direct payment for a purchase order: Dr GIT, Cr Bank. No payable."""
    _name = 'purchase.bank.payment'
    _description = 'Purchase Bank Payment'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    source = fields.Selection(
        [('local', 'Direct Payment')], default='local', required=True,
        readonly=True, copy=False,
        help="Where the payment comes from. Other modules (LC) add their own "
             "and keep their rows in sync; those rows cannot be edited here.")
    external_amount_company = fields.Monetary(
        string="Amount Paid (Company Currency)",
        currency_field='company_currency_id',
        help="Set by the module that owns a non-local payment: the real "
             "amount that left the bank.")
    rate = fields.Float(
        string="Rate", digits=(12, 4), compute='_compute_amount_company',
        store=True)
    purchase_id = fields.Many2one(
        'purchase.order', string="Purchase Order", required=True,
        ondelete='restrict', index=True, tracking=True)
    partner_id = fields.Many2one(
        related='purchase_id.partner_id', store=True, string="Supplier")
    company_id = fields.Many2one(
        related='purchase_id.company_id', store=True)
    currency_id = fields.Many2one(
        related='purchase_id.currency_id', store=True, string="Currency")
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', string="Company Currency")
    journal_id = fields.Many2one(
        'account.journal', string="Bank", required=True, tracking=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]")
    git_account_id = fields.Many2one(
        'account.account', string="GIT Account", required=True, tracking=True)
    amount = fields.Monetary(
        string="Amount", currency_field='currency_id', required=True,
        tracking=True)
    date = fields.Date(
        default=fields.Date.context_today, required=True, tracking=True)
    memo = fields.Char(string="Reference")
    amount_company = fields.Monetary(
        string="Amount (Company Currency)",
        currency_field='company_currency_id',
        compute='_compute_amount_company', store=True)
    move_id = fields.Many2one(
        'account.move', string="Journal Entry", readonly=True, copy=False)
    state = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Paid'), ('cancelled', 'Cancelled')],
        default='draft', tracking=True, copy=False)

    rate_display = fields.Char(
        string="Rate", compute='_compute_rate_display',
        help="Company-currency units per 1 unit of the payment currency, "
             "shown with the currency symbol (for example 190.5500 Br).")

    @api.depends('rate', 'company_currency_id')
    def _compute_rate_display(self):
        for rec in self:
            symbol = rec.company_currency_id.symbol or ''
            rec.rate_display = f"{rec.rate:,.4f} {symbol}".strip() if rec.rate else ""

    @api.depends('amount', 'currency_id', 'company_id', 'date', 'source',
                 'external_amount_company')
    def _compute_amount_company(self):
        for rec in self:
            if rec.source != 'local':
                rec.amount_company = rec.external_amount_company
            else:
                rec.amount_company = rec.currency_id._convert(
                    rec.amount, rec.company_currency_id, rec.company_id,
                    rec.date or fields.Date.context_today(rec))
            rec.rate = rec.amount_company / rec.amount if rec.amount else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'purchase.bank.payment') or 'New'
            po = self.env['purchase.order'].browse(vals.get('purchase_id'))
            if po and not vals.get('amount'):
                vals['amount'] = po.bank_remaining_amount
            if po and not vals.get('git_account_id'):
                last = self.search(
                    [('purchase_id', '=', po.id), ('state', '=', 'posted')],
                    limit=1)
                vals['git_account_id'] = last.git_account_id.id or False
        return super().create(vals_list)

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("The payment amount must be positive."))

    def action_post(self):
        for rec in self:
            if rec.source != 'local':
                raise UserError(_("This payment is managed by its source."))
            if rec.state != 'draft':
                continue
            po = rec.purchase_id
            if not po.x_direct_pay:
                raise UserError(_(
                    "%s is set to use vendor bills, not direct payments.",
                    po.name))
            if po.state not in ('purchase', 'done'):
                raise UserError(_(
                    "Confirm the purchase order %s before paying it.", po.name))
            if float_compare(
                    rec.amount, po.bank_remaining_amount,
                    precision_rounding=po.currency_id.rounding) > 0:
                raise UserError(_(
                    "This payment is more than what is left to pay on %(po)s "
                    "(%(left)s).", po=po.name, left=po.bank_remaining_amount))
            bank = rec.journal_id.default_account_id
            if not bank:
                raise UserError(_("The bank journal has no default account."))
            foreign = rec.currency_id != rec.company_currency_id
            amt = rec.amount_company
            ref = _("%(pay)s - %(po)s", pay=rec.name, po=po.name)
            cur = rec.currency_id.id if foreign else False
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': rec.journal_id.id,
                'date': rec.date,
                'ref': ref,
                'line_ids': [
                    (0, 0, {
                        'name': ref, 'account_id': rec.git_account_id.id,
                        'partner_id': po.partner_id.id,
                        'debit': amt, 'credit': 0.0,
                        'currency_id': cur,
                        'amount_currency': rec.amount if foreign else 0.0,
                    }),
                    (0, 0, {
                        'name': ref, 'account_id': bank.id,
                        'partner_id': po.partner_id.id,
                        'debit': 0.0, 'credit': amt,
                        'currency_id': cur,
                        'amount_currency': -rec.amount if foreign else 0.0,
                    }),
                ],
            })
            move.action_post()
            rec.write({'move_id': move.id, 'state': 'posted'})

    def action_cancel(self):
        for rec in self:
            if rec.source != 'local' and not self.env.context.get('bp_sync'):
                raise UserError(_(
                    "This payment comes from its Letter of Credit. Cancel "
                    "the LC settlement instead."))
            if rec.state == 'posted' and rec.move_id:
                rev = rec.move_id._reverse_moves(
                    default_values_list=[{
                        'date': fields.Date.context_today(rec),
                        'ref': _("Reversal of %s", rec.move_id.name),
                    }], cancel=False)
                rev._post()
            rec.state = 'cancelled'

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'account.move',
            'res_id': self.move_id.id, 'view_mode': 'form',
        }

    def unlink(self):
        if self.filtered(lambda r: r.state == 'posted'):
            raise UserError(_("A posted payment cannot be deleted. Cancel it."))
        return super().unlink()
