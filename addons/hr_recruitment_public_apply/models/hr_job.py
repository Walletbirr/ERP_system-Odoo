# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date, html2plaintext

PREVIEW_LENGTH = 160


class HrJob(models.Model):
    _inherit = 'hr.job'

    portal_publish_state = fields.Selection(
        selection=[('published', 'Published'), ('unpublished', 'Unpublished')],
        string='Publish on Careers Portal?',
        default='published',
        required=True,
        help='Published jobs are listed and open for applications on the '
             'public Careers Portal (/careers), independent of the Odoo '
             'Website app. Unpublished jobs stay hidden from the portal '
             'even while Active.',
    )
    portal_application_deadline = fields.Date(
        string='Application Deadline',
        help='Last day candidates can apply on the public Careers Portal. '
             'Once this date has passed, the job is automatically '
             'unpublished and stops accepting new applications - even if '
             'the Publish toggle above still says "Published". Leave '
             'empty for a job that stays open indefinitely.',
    )
    portal_application_deadline_display = fields.Char(
        string='Application Deadline (Display)',
        compute='_compute_portal_application_deadline_display',
        help='Human-readable version of the Application Deadline, used on '
             'the public Careers Portal listing and detail pages.',
    )
    portal_is_deadline_passed = fields.Boolean(
        string='Deadline Passed',
        compute='_compute_portal_is_deadline_passed',
        help='True once the Application Deadline date is in the past.',
    )
    portal_job_description_preview = fields.Char(
        string='Description Preview',
        compute='_compute_portal_job_description_preview',
        help='Auto-generated plain-text preview of the standard "Job '
             'Summary" field, shown under the job title on /careers.',
    )
    portal_is_published = fields.Boolean(
        string='Published on Careers Portal',
        compute='_compute_portal_is_published',
        inverse='_inverse_portal_is_published',
        search='_search_portal_is_published',
        help='Toggle version of "Publish on Careers Portal?", used for the '
             'inline switch on the Job Positions kanban cards.',
    )

    def _compute_portal_is_published(self):
        for job in self:
            job.portal_is_published = job.portal_publish_state == 'published'

    def _inverse_portal_is_published(self):
        for job in self:
            job.portal_publish_state = 'published' if job.portal_is_published else 'unpublished'

    def _search_portal_is_published(self, operator, value):
        want_published = value if operator == '=' else not value
        state = 'published' if want_published else 'unpublished'
        return [('portal_publish_state', '=', state)]

    def _compute_portal_job_description_preview(self):
        for job in self:
            plain = html2plaintext(job.description or '').strip()
            if len(plain) > PREVIEW_LENGTH:
                plain = plain[:PREVIEW_LENGTH].rsplit(' ', 1)[0] + '…'
            job.portal_job_description_preview = plain

    @api.depends('portal_application_deadline')
    def _compute_portal_is_deadline_passed(self):
        today = fields.Date.context_today(self)
        for job in self:
            job.portal_is_deadline_passed = bool(
                job.portal_application_deadline and job.portal_application_deadline < today
            )

    @api.depends('portal_application_deadline')
    def _compute_portal_application_deadline_display(self):
        for job in self:
            job.portal_application_deadline_display = (
                format_date(self.env, job.portal_application_deadline, date_format='MMMM d, y')
                if job.portal_application_deadline else False
            )

    # ------------------------------------------------------------------
    # Auto-unpublish when the deadline is met
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        jobs = super().create(vals_list)
        jobs._auto_unpublish_if_deadline_passed()
        return jobs

    def write(self, vals):
        # Block manually (re)publishing a job whose deadline has already
        # passed, unless this same write also pushes the deadline forward.
        wants_published = None
        if 'portal_publish_state' in vals:
            wants_published = vals['portal_publish_state'] == 'published'
        elif 'portal_is_published' in vals:
            wants_published = bool(vals['portal_is_published'])

        if wants_published and 'portal_application_deadline' not in vals:
            today = fields.Date.context_today(self)
            expired = self.filtered(
                lambda j: j.portal_application_deadline
                and j.portal_application_deadline < today
            )
            if expired:
                raise UserError(_(
                    'Cannot publish %s on the Careers Portal: the '
                    'application deadline has already passed. Extend or '
                    'clear the deadline first, then publish again.'
                ) % ', '.join(expired.mapped('name')))

        res = super().write(vals)

        if 'portal_application_deadline' in vals:
            self._auto_unpublish_if_deadline_passed()

        return res

    def _auto_unpublish_if_deadline_passed(self):
        """Flip Published -> Unpublished for any of these jobs whose
        deadline is already in the past. Called right after create/write
        so the change is reflected immediately, without waiting on the
        cron below."""
        today = fields.Date.context_today(self)
        expired = self.filtered(
            lambda j: j.portal_publish_state == 'published'
            and j.portal_application_deadline
            and j.portal_application_deadline < today
        )
        if expired:
            expired.write({'portal_publish_state': 'unpublished'})

    @api.model
    def _cron_unpublish_expired_jobs(self):
        """Safety net: unpublishes jobs whose deadline passes with nobody
        touching the record (create/write already handle the interactive
        cases). Scheduled hourly, see data/ir_cron_data.xml."""
        today = fields.Date.context_today(self)
        expired = self.search([
            ('portal_publish_state', '=', 'published'),
            ('portal_application_deadline', '!=', False),
            ('portal_application_deadline', '<', today),
        ])
        if expired:
            expired.write({'portal_publish_state': 'unpublished'})
