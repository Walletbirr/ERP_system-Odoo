from urllib.parse import quote

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrderPaymentProof(models.Model):
    _name = 'sale.order.payment.proof'
    _description = 'Sales Order Payment Proof'
    _order = 'uploaded_date desc, id desc'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    proof_file = fields.Binary(
        string='Proof File',
        attachment=True,
    )
    proof_filename = fields.Char(string='Filename')
    notes = fields.Text(
        string='Notes',
        help='Free text - any context the salesperson wants to add for '
             'Accounting (e.g. which bank/wallet the transfer came in '
             'on).',
    )
    state = fields.Selection(
        [('pending', 'Pending'),
         ('submitted', 'Submitted')],
        string='Status',
        default='pending',
        required=True,
        copy=False,
        help='Pending: the salesperson is still attaching/fixing the '
             'file, Accounting is not expected to look at it yet. '
             'Submitted: the salesperson has confirmed the file is '
             "ready - Accounting can now open/download it before "
             "creating the invoice. There is no approval step here: "
             "the payment already happened, so this is purely a "
             "\"ready to look at\" flag, not a decision Accounting "
             "makes about the proof itself.",
    )
    uploaded_by = fields.Many2one(
        'res.users',
        string='Uploaded By',
        default=lambda self: self.env.user,
        readonly=True,
    )
    uploaded_date = fields.Datetime(
        string='Uploaded On',
        default=fields.Datetime.now,
        readonly=True,
    )
    submitted_date = fields.Datetime(
        string='Submitted On',
        readonly=True,
        copy=False,
    )
    download_link = fields.Html(
        string='File',
        compute='_compute_download_link',
        sanitize=False,
        help='A ready-to-click filename + download icon, built server-'
             'side instead of relying on the standard Binary widget. '
             "The Binary widget's read-only rendering in list views "
             "depends on the browser having already fetched the actual "
             "file content; Odoo's list views fetch binary fields in a "
             'bandwidth-saving "size only" mode by default, so a plain '
             'read-only Binary cell can end up stuck showing something '
             'like "1.05 Mb" instead of the filename, with no way to '
             "click through to download - which is exactly what was "
             "happening for Accounting. This field sidesteps that "
             "entirely: it always resolves to a real, working link to "
             "the same file, for every audience, on first render.",
    )

    @api.depends('proof_file', 'proof_filename')
    def _compute_download_link(self):
        for proof in self:
            # A brand-new, not-yet-saved line has no usable id to build
            # a /web/content URL from yet - nothing to link to until
            # it's actually saved.
            if proof.proof_file and isinstance(proof.id, int):
                filename = proof.proof_filename or _('payment_proof')
                url = '/web/content/sale.order.payment.proof/%s/proof_file?download=true&filename=%s' % (
                    proof.id, quote(filename))
                proof.download_link = Markup(
                    '<a href="%s" target="_blank" class="o_form_uri">'
                    '<i class="fa fa-download me-1"/>%s</a>'
                ) % (url, escape(filename))
            else:
                proof.download_link = False

    def action_submit(self):
        for proof in self:
            if not proof.proof_file:
                raise UserError(_(
                    'Attach the payment proof file before submitting it '
                    'to Accounting.'))
        self.write({
            'state': 'submitted',
            'submitted_date': fields.Datetime.now(),
        })

    def action_reopen(self):
        """Self-service: the salesperson can pull a submitted line back
        to fix a mistake (wrong file, wrong notes) without needing
        anyone's permission - there's no approval decision being undone
        here, just a "not ready yet after all" correction."""
        self.write({
            'state': 'pending',
            'submitted_date': False,
        })

    @api.constrains('sale_order_id')
    def _check_order_is_confirmed(self):
        for proof in self:
            if proof.sale_order_id.state != 'sale':
                raise UserError(_(
                    'A payment proof can only be added to a confirmed '
                    'Sales Order.'))
