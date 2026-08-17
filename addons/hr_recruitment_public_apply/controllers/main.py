# -*- coding: utf-8 -*-
import base64
import logging
import re

from werkzeug.utils import redirect

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = ('.pdf', '.doc', '.docx')
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
SOURCE_NAME = 'Company Careers Portal'
DEFAULT_BRAND_RGB = '113, 75, 103'  # matches the default #714B67 accent


class PublicJobApplicationController(http.Controller):
    """Standalone, login-free job application flow.

    Does not depend on the Website app - templates render full HTML
    documents so this works even on a bare Odoo instance, and the
    /careers pages can be reverse-proxied on a subdomain or embedded
    via <iframe> on an external site.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_open_jobs(self):
        Job = request.env['hr.job'].sudo()
        today = fields.Date.context_today(Job)
        return Job.search([
            ('active', '=', True),
            ('portal_publish_state', '=', 'published'),
            '|', ('portal_application_deadline', '=', False),
                 ('portal_application_deadline', '>=', today),
        ], order='name asc')

    def _get_valid_job(self, job_id):
        job = request.env['hr.job'].sudo().browse(job_id)
        today = fields.Date.context_today(job)
        deadline_ok = (
            not job.portal_application_deadline
            or job.portal_application_deadline >= today
        )
        if not job.exists() or not job.active or job.portal_publish_state != 'published' or not deadline_ok:
            return request.env['hr.job']
        return job

    def _get_or_create_source(self):
        """utm.source may not exist on every install; degrade quietly."""
        try:
            Source = request.env['utm.source'].sudo()
            source = Source.search([('name', '=', SOURCE_NAME)], limit=1)
            if not source:
                source = Source.create({'name': SOURCE_NAME})
            return source
        except Exception:
            _logger.warning('utm.source not available, skipping source tagging', exc_info=True)
            return False

    def _get_or_create_candidate(self, job, name, email, phone):
        """Odoo 18 moved personal candidate data (name/email/phone) out of
        hr.applicant and into a dedicated hr.candidate model, linked via
        hr.applicant.candidate_id. We look up an existing candidate by
        email first (repeat applicants), otherwise create one - always in
        the same company as the job, to avoid the multi-company
        validation error Odoo raises when applicant/candidate companies
        differ.
        """
        Candidate = request.env['hr.candidate'].sudo()
        company_id = job.company_id.id or request.env.user.company_id.id

        candidate = Candidate.search([('email_from', '=', email)], limit=1)
        if candidate:
            # Same email applying again: refresh name/phone to this
            # submission's values rather than silently keeping stale data
            # from an earlier application.
            update_vals = {}
            if name and candidate.partner_name != name:
                update_vals['partner_name'] = name
            if phone and candidate.partner_phone != phone:
                update_vals['partner_phone'] = phone
            if update_vals:
                candidate.write(update_vals)
            return candidate

        return Candidate.create({
            'partner_name': name,
            'email_from': email,
            'partner_phone': phone,
            'company_id': company_id,
        })

    def _get_branding_company(self):
        """The company whose logo/accent color brand the public pages."""
        return request.env.company.sudo()

    def _hex_to_rgb(self, hex_color):
        """'#714B67' -> '113, 75, 103', used for rgba() overlays/glows in CSS."""
        if hex_color:
            h = hex_color.strip().lstrip('#')
            if len(h) == 3:
                h = ''.join(c * 2 for c in h)
            if len(h) == 6 and re.fullmatch(r'[0-9A-Fa-f]{6}', h):
                return '%d, %d, %d' % tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        return DEFAULT_BRAND_RGB

    def _get_branding_context(self):
        company = self._get_branding_company()
        return {
            'company': company,
            'brand_rgb': self._hex_to_rgb(company.careers_portal_color),
        }

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @http.route(['/careers', '/careers/'], type='http', auth='public',
                website=False, csrf=False, sitemap=False)
    def careers_list(self, **kwargs):
        jobs = self._get_open_jobs()
        departments = sorted({job.department_id.name for job in jobs if job.department_id})
        return request.render(
            'hr_recruitment_public_apply.careers_list_template',
            {'jobs': jobs, 'departments': departments, **self._get_branding_context()},
        )

    @http.route(['/careers/apply/<int:job_id>'], type='http', auth='public',
                website=False, csrf=True, sitemap=False)
    def careers_apply_form(self, job_id, **kwargs):
        job = self._get_valid_job(job_id)
        if not job:
            return request.not_found()
        return request.render(
            'hr_recruitment_public_apply.careers_apply_form_template',
            {
                'job': job,
                'error': kwargs.get('error'),
                'post': {},
                **self._get_branding_context(),
            },
        )

    @http.route(['/careers/logo'], type='http', auth='public',
                website=False, sitemap=False)
    def careers_logo(self, **kwargs):
        company = self._get_branding_company()
        if not company.logo:
            return request.not_found()
        stream = request.env['ir.binary']._get_image_stream_from(
            company, field_name='logo'
        )
        return stream.get_response()

    @http.route(['/careers/apply/<int:job_id>/submit'], type='http',
                auth='public', website=False, methods=['POST'], csrf=True)
    def careers_apply_submit(self, job_id, **post):
        job = self._get_valid_job(job_id)
        if not job:
            return request.not_found()

        # Honeypot: hidden field via CSS, real users never fill it in.
        if post.get('company_website_hp'):
            _logger.info('Blocked suspected spam submission for job %s', job_id)
            return redirect('/careers/apply/%s/thankyou' % job_id)

        name = (post.get('partner_name') or '').strip()
        email = (post.get('email_from') or '').strip()
        phone = (post.get('partner_phone') or '').strip()
        cover_letter = (post.get('cover_letter') or '').strip()

        branding_ctx = self._get_branding_context()

        def render_with_error(msg):
            return request.render(
                'hr_recruitment_public_apply.careers_apply_form_template',
                {'job': job, 'error': msg, 'post': post, **branding_ctx},
            )

        if not name or not email:
            return render_with_error('Name and email are required.')

        cv_file = request.httprequest.files.get('cv_file')
        attachment_vals = None
        if not cv_file or not cv_file.filename:
            return render_with_error('Please attach your CV / resume.')

        filename = cv_file.filename
        ext = ('.' + filename.rsplit('.', 1)[-1].lower()) if '.' in filename else ''
        if ext not in ALLOWED_EXTENSIONS:
            return render_with_error('CV must be a PDF, DOC or DOCX file.')

        content = cv_file.read()
        if len(content) > MAX_FILE_SIZE:
            return render_with_error('CV file is too large (max 5 MB).')

        try:
            company_id = job.company_id.id or request.env.user.company_id.id
            candidate = self._get_or_create_candidate(job, name, email, phone)
            source = self._get_or_create_source()

            applicant_vals = {
                'candidate_id': candidate.id,
                'job_id': job.id,
                'department_id': job.department_id.id,
                'company_id': company_id,
            }
            if source:
                applicant_vals['source_id'] = source.id

            Applicant = request.env['hr.applicant'].sudo()
            applicant = Applicant.create(applicant_vals)

            attachment_vals = {
                'name': filename,
                'datas': base64.b64encode(content),
                'res_model': 'hr.applicant',
                'res_id': applicant.id,
                'type': 'binary',
            }
            request.env['ir.attachment'].sudo().create(attachment_vals)

            if cover_letter:
                applicant.sudo().message_post(body=cover_letter)

        except Exception:
            _logger.exception(
                'Failed to create applicant from public careers portal (job_id=%s)', job_id
            )
            return render_with_error(
                'Something went wrong submitting your application. '
                'Please try again in a moment, or contact us directly.'
            )

        return redirect('/careers/apply/%s/thankyou' % job_id)

    @http.route(['/careers/apply/<int:job_id>/thankyou'], type='http',
                auth='public', website=False, sitemap=False)
    def careers_apply_thankyou(self, job_id, **kwargs):
        job = request.env['hr.job'].sudo().browse(job_id)
        return request.render(
            'hr_recruitment_public_apply.careers_thank_you_template',
            {'job': job, **self._get_branding_context()},
        )
