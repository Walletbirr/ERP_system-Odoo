from odoo import models, fields, api


class LCAccountSetupRequest(models.Model):
    _name = 'lc.account.setup.request'
    _description = 'LC Chart of Accounts Setup Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    lc_id = fields.Many2one(
        'lc.management',
        string="Letter of Credit",
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    account_purpose = fields.Selection([
        ('fee', 'GIT Account (LC costs)'),
        ('vat', 'Opening / Settlement VAT Account'),
        ('other', 'Other Account'),
    ], string="Account Needed For", required=True, default='fee', tracking=True)

    suggested_account_name = fields.Char(
        string="Suggested Account Name / Code",
        help="Optional hint for the accountant about what to name or code the new GL account."
    )
    note = fields.Text(string="Note to Accountant")

    requested_by_id = fields.Many2one(
        'res.users', string="Requested By",
        default=lambda self: self.env.user, readonly=True
    )
    assigned_accountant_id = fields.Many2one(
        'res.users', string="Assigned Accountant", required=True, tracking=True,
        default=lambda self: self.env.company.lc_default_accountant_id
    )

    state = fields.Selection([
        ('sent', 'Sent'),
        ('viewed', 'Viewed by Accountant'),
        ('completed', 'Account Created'),
    ], default='sent', required=True, tracking=True)

    sent_date = fields.Datetime(string="Sent On", default=fields.Datetime.now, readonly=True)
    viewed_date = fields.Datetime(string="First Viewed On", readonly=True)
    completed_date = fields.Datetime(string="Completed On", readonly=True)

    response_time_hours = fields.Float(
        string="Time to First View (hrs)", compute='_compute_durations', store=True,
        help="Hours between the request being sent and the accountant first opening it."
    )
    resolution_time_hours = fields.Float(
        string="Time to Completion (hrs)", compute='_compute_durations', store=True,
        help="Hours between the request being sent and the account actually being created."
    )

    can_mark_completed = fields.Boolean(
        string="Can Mark Completed",
        compute='_compute_can_mark_completed',
        help="Technical field controlling who sees the 'Mark Account Created' "
             "button: the accountant it was assigned to, or an administrator - "
             "never the person who sent the request (unless they're also an admin)."
    )

    @api.depends('assigned_accountant_id')
    def _compute_can_mark_completed(self):
        is_admin = self.env.user.has_group('base.group_system')
        for rec in self:
            rec.can_mark_completed = is_admin or rec.assigned_accountant_id.id == self.env.uid

    @api.depends('sent_date', 'viewed_date', 'completed_date')
    def _compute_durations(self):
        for rec in self:
            rec.response_time_hours = (
                (rec.viewed_date - rec.sent_date).total_seconds() / 3600.0
                if rec.sent_date and rec.viewed_date else 0.0
            )
            rec.resolution_time_hours = (
                (rec.completed_date - rec.sent_date).total_seconds() / 3600.0
                if rec.sent_date and rec.completed_date else 0.0
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._notify_accountant()
        return records

    def _purpose_label(self):
        self.ensure_one()
        return dict(self._fields['account_purpose'].selection).get(self.account_purpose)

    def _notify_accountant(self):
        for rec in self:
            if not rec.assigned_accountant_id:
                continue
            partner = rec.assigned_accountant_id.partner_id
            rec.message_subscribe(partner_ids=partner.ids)
            rec.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=f"Create GL account for LC {rec.lc_id.name}",
                note=rec.note or (
                    f"Please create the {rec._purpose_label()} for {rec.lc_id.name} "
                    f"so it can be opened/settled."
                ),
                user_id=rec.assigned_accountant_id.id,
            )
            rec.message_post(
                body=(
                    f"Account setup requested for <b>{rec.lc_id.name}</b> "
                    f"({rec._purpose_label()})."
                    + (f"<br/>Suggested name/code: {rec.suggested_account_name}" if rec.suggested_account_name else "")
                ),
                partner_ids=partner.ids,
            )
            self.env['bus.bus']._sendone(partner, 'simple_notification', {
                'type': 'info',
                'title': 'Account Setup Request',
                'message': (
                    f"{self.env.user.name} needs a {rec._purpose_label()} "
                    f"created for {rec.lc_id.name}."
                ),
                'sticky': True,
                'className': 'o_lc_request_notification',
            })
            self.env.user._bus_send('simple_notification', {
                'type': 'success',
                'title': 'Request Sent',
                'message': f"Account setup request for {rec.lc_id.name} sent to {rec.assigned_accountant_id.name}.",
            })

    def read(self, fields=None, load='_classic_read'):
        """Best-effort automatic 'viewed' tracking: the first time the
        assigned accountant opens this record, stamp viewed_date and flip
        the state - a real signal rather than relying on them remembering
        to click something. This only fires once per request (guarded by
        the state=='sent' check), so normal re-reads are cheap no-ops."""
        from odoo import fields as odoo_fields
        result = super().read(fields=fields, load=load)
        if not self.env.context.get('lc_skip_view_tracking'):
            to_mark = self.filtered(
                lambda r: r.state == 'sent' and r.assigned_accountant_id.id == self.env.uid
            )
            if to_mark:
                to_mark.with_context(lc_skip_view_tracking=True).write({
                    'state': 'viewed',
                    'viewed_date': odoo_fields.Datetime.now(),
                })
        return result

    def action_close(self):
        """Footer 'Send' button on the create dialog. Odoo auto-saves the
        record (which triggers create() -> _notify_accountant()) before
        running this, so by the time we get here the request has already
        been sent - this just closes the dialog."""
        return {'type': 'ir.actions.act_window_close'}

    def action_mark_completed(self):
        for rec in self.filtered(lambda r: r.state != 'completed'):
            rec.write({
                'state': 'completed',
                'completed_date': fields.Datetime.now(),
            })
            rec.activity_ids.action_feedback(feedback="GL account created.")

    @api.model
    def _auto_complete_for_lc(self, lc, purpose):
        """Called from lc.management.write() when the corresponding account
        field gets filled in - closes out any matching open request
        automatically, so the accountant doesn't have to remember to come
        back and mark it done by hand."""
        pending = self.search([
            ('lc_id', '=', lc.id),
            ('account_purpose', '=', purpose),
            ('state', '!=', 'completed'),
        ])
        pending.action_mark_completed()
