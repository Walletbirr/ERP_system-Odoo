from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PaperInvoiceVoidWizard(models.TransientModel):
    """Salesperson: void a spoiled paper invoice. One step and final: it
    shows as "Void" in Accounting's Invoices list at once."""
    _name = 'paper.invoice.void.wizard'
    _description = 'Void Paper Invoice'

    paper_number = fields.Char(string="Paper Invoice No.", required=True,
                               help="Number printed on the spoiled paper "
                                    "invoice, e.g. CSI-1560.")
    void_date = fields.Date(string="Date", required=True,
                            default=fields.Date.context_today)
    branch_id = fields.Many2one(
        'stock.warehouse', string="Branch",
        default=lambda self: self.env['sale.order']._default_sale_branch_id(),
        domain="[('company_id', '=', company_id)]")
    reason = fields.Text(string="Reason", required=True,
                         help="Why the paper invoice was spoiled.")
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company)

    @api.model
    def _open(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Void Paper Invoice'),
            'res_model': self._name,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_void(self):
        self.ensure_one()
        number = (self.paper_number or '').strip()
        reason = (self.reason or '').strip()
        if not number:
            raise UserError(_("Enter the paper invoice number."))
        if not reason:
            raise UserError(_("Enter the reason."))
        if self.void_date > fields.Date.context_today(self):
            raise ValidationError(_("The date cannot be in the future."))
        self.env['account.move']._bridge_create_void(
            self.company_id, number, self.void_date, self.branch_id, reason)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("Paper invoice %s is now void.", number),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
