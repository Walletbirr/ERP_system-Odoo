from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class PaymentProofApproveWizard(models.TransientModel):
    _name = 'sale.order.payment.proof.approve.wizard'
    _description = 'Approve Payment Proof'

    # Explicit short relation (PostgreSQL 63-character identifier limit).
    proof_ids = fields.Many2many(
        'sale.order.payment.proof',
        'payment_proof_approve_wiz_rel', 'wizard_id', 'proof_id',
        string='Payment Proofs', required=True)
    company_id = fields.Many2one(
        'res.company', compute='_compute_company_id')
    currency_id = fields.Many2one(
        'res.currency', compute='_compute_company_id')
    journal_id = fields.Many2one(
        'account.journal', string='Bank / Cash Journal',
        domain="[('type', 'in', ('bank', 'cash')), "
               "('company_id', '=', company_id)]",
        help="The bank (or cash) journal the customer's payment arrived in. "
             "It is preselected when the invoice of this order is paid.")
    multi_bank = fields.Boolean(
        string='Multi Bank',
        help="Tick it when the payment was split between several banks. "
             "You then enter each bank and the amount it received; the "
             "total can never be more than the order total.")
    can_split = fields.Boolean(compute='_compute_company_id')
    bank_line_ids = fields.One2many(
        'sale.order.payment.proof.approve.wizard.line', 'wizard_id',
        string='Banks',
        help="Every bank / cash journal the customer's payment went into, "
             "with the amount deposited in each. They will be listed on the "
             "invoice's Pay dialog.")
    sale_order_id = fields.Many2one(
        'sale.order', string='Order', compute='_compute_company_id')
    partner_id = fields.Many2one(
        'res.partner', string='Customer', compute='_compute_company_id')
    order_total = fields.Monetary(
        string='Order Total', currency_field='currency_id',
        compute='_compute_company_id')
    bank_total = fields.Monetary(
        string='Total Deposited', currency_field='currency_id',
        compute='_compute_bank_total')
    bank_difference = fields.Monetary(
        string='Still to Enter', currency_field='currency_id',
        compute='_compute_bank_total',
        help="Order total minus the amounts entered. Zero when the banks "
             "cover the whole order; negative when more was entered.")
    bank_state = fields.Selection(
        [('empty', 'Nothing entered'), ('partial', 'Partial'),
         ('full', 'Complete'), ('over', 'Too much')],
        compute='_compute_bank_total')
    preview_html = fields.Html(
        string='Files', compute='_compute_preview_html', sanitize=False)

    @api.depends('proof_ids')
    def _compute_company_id(self):
        for wizard in self:
            order = wizard.proof_ids[:1].sale_order_id
            wizard.company_id = order.company_id or self.env.company
            wizard.currency_id = (
                order.currency_id or wizard.company_id.currency_id)
            wizard.order_total = order.amount_total if len(
                wizard.proof_ids) == 1 else 0.0
            wizard.sale_order_id = order if len(wizard.proof_ids) == 1 \
                else False
            wizard.partner_id = order.partner_id if len(
                wizard.proof_ids) == 1 else False
            wizard.can_split = len(wizard.proof_ids) == 1

    @api.depends('bank_line_ids.amount', 'order_total', 'currency_id')
    def _compute_bank_total(self):
        for wizard in self:
            total = sum(wizard.bank_line_ids.mapped('amount'))
            wizard.bank_total = total
            currency = wizard.currency_id
            wizard.bank_difference = currency.round(
                wizard.order_total - total) if currency else 0.0
            if not currency or currency.is_zero(total):
                wizard.bank_state = 'empty'
            elif currency.compare_amounts(total, wizard.order_total) > 0:
                wizard.bank_state = 'over'
            elif currency.is_zero(wizard.bank_difference):
                wizard.bank_state = 'full'
            else:
                wizard.bank_state = 'partial'

    @api.depends('proof_ids')
    def _compute_preview_html(self):
        for wizard in self:
            parts = [Markup('<span class="me-3">%s</span>') % Markup(proof.preview_links)
                     for proof in wizard.proof_ids if proof.preview_links]
            wizard.preview_html = Markup('').join(parts) if parts else False

    def action_approve(self):
        self.ensure_one()
        currency = self.currency_id
        if not self.multi_bank:
            if not self.journal_id:
                raise UserError(_(
                    "Select the bank the customer's payment arrived in."))
            # One bank: exactly what Approve always did. The whole order
            # amount went into it, the invoice's Pay dialog is the
            # standard one with this journal preselected.
            self.proof_ids.action_approve(journal=self.journal_id)
            return {'type': 'ir.actions.act_window_close'}

        lines = self.bank_line_ids
        if not lines:
            raise UserError(_(
                "Add at least one bank and the amount it received."))
        if lines.filtered(lambda l: not l.journal_id):
            raise UserError(_("Choose the bank on every row."))
        if len(lines.journal_id) != len(lines):
            raise UserError(_(
                "The same bank is listed twice. Use one row per bank."))
        for line in lines:
            if currency.compare_amounts(line.amount, 0) <= 0:
                raise UserError(_(
                    "Enter the amount received in %s (it must be greater "
                    "than zero).", line.journal_id.display_name))
        total = sum(lines.mapped('amount'))
        if currency.compare_amounts(total, self.order_total) > 0:
            raise UserError(_(
                "The banks add up to %(entered)s, which is more than the "
                "order total (%(total)s). Correct the amounts.",
                entered=formatLang(self.env, total, currency_obj=currency),
                total=formatLang(
                    self.env, self.order_total, currency_obj=currency)))
        self.proof_ids.action_approve(
            bank_lines=[(line.journal_id, line.amount) for line in lines])
        return {'type': 'ir.actions.act_window_close'}


class PaymentProofApproveWizardLine(models.TransientModel):
    _name = 'sale.order.payment.proof.approve.wizard.line'
    _description = 'Approve Payment Proof - Bank Row'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'sale.order.payment.proof.approve.wizard', required=True,
        ondelete='cascade')
    sequence = fields.Integer(default=10)
    journal_id = fields.Many2one(
        'account.journal', string='Bank', required=True,
        domain="[('type', 'in', ('bank', 'cash'))]")
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    amount = fields.Monetary(
        string='Amount Received', required=True,
        currency_field='currency_id')
