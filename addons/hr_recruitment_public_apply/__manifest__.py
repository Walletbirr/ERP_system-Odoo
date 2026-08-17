{
    'name': 'Public Job Application Portal',
    'version': '18.0.1.4.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Standalone public web form for job applications, independent of the Website app',
    'description': """
Public Job Application Portal
==============================
Adds a lightweight, standalone public form (no Odoo Website app required)
so candidates can browse open positions and submit applications directly
into the Recruitment pipeline (hr.applicant), CV attached automatically.

Routes
------
/careers                          List of open, published positions
/careers/apply/<job_id>            Application form for one job
/careers/apply/<job_id>/submit     Form handler (POST)
/careers/apply/<job_id>/thankyou   Confirmation page

Features
--------
* No login required for applicants (fully public, anonymous form)
* Per-job "Publish on Careers Portal" toggle on the Job Position form,
  so HR controls exactly which vacancies are publicly visible
* Optional "Application Deadline" per job: shown on the listing card, the
  detail page, the kanban card and the form view; once the date passes
  the job is automatically unpublished (immediately on save, plus an
  hourly cron as a safety net) and stops accepting applications
* CV upload (PDF / DOC / DOCX, 5MB limit) attached to the applicant record
* Honeypot hidden field to filter basic spam bots
* CSRF protected submission
* Auto-tags every submission with a "Company Careers Portal" UTM source,
  so recruitment reporting can compare this channel to others
* Self-contained HTML pages (no dependency on the Website app's layout),
  so it can be hosted on a subdomain or embedded via <iframe> on an
  external company website built on any other platform
""",
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['hr_recruitment'],
    'data': [
        'data/ir_cron_data.xml',
        'views/hr_job_views.xml',
        'views/res_company_views.xml',
        'views/templates.xml',
    ],
    'installable': True,
    'application': False,
}
