from markupsafe import Markup

from odoo import api, fields, models


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
    journal_id = fields.Many2one(
        'account.journal', string='Payment Journal', required=True,
        domain="[('type', 'in', ('bank', 'cash')), "
               "('company_id', '=', company_id)]",
        help="The journal the customer's payment went into. It will be "
             "preselected when the invoice is paid.")
    preview_html = fields.Html(
        string='Files', compute='_compute_preview_html', sanitize=False)

    @api.depends('proof_ids')
    def _compute_company_id(self):
        for wizard in self:
            wizard.company_id = (
                wizard.proof_ids[:1].sale_order_id.company_id
                or self.env.company)

    @api.depends('proof_ids')
    def _compute_preview_html(self):
        for wizard in self:
            parts = [Markup('<span class="me-3">%s</span>') % Markup(proof.preview_links)
                     for proof in wizard.proof_ids if proof.preview_links]
            wizard.preview_html = Markup('').join(parts) if parts else False

    def action_approve(self):
        self.ensure_one()
        self.proof_ids.action_approve(self.journal_id)
        return {'type': 'ir.actions.act_window_close'}
