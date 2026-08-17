# Public Job Application Portal (Odoo 18 Community)

A standalone, login-free public job application form. Solves the manual
"HR retypes CVs into Odoo" problem: candidates apply on a public page,
and an `hr.applicant` record (with CV attached) is created automatically
in the correct Job Position's pipeline.

Does **not** depend on the Odoo Website app — it works even if your main
company website is built on something else entirely.

## Installation

1. Copy the `hr_recruitment_public_apply` folder into your Odoo 18
   `addons` path (e.g. `/mnt/extra-addons/`).
2. Restart the Odoo service.
3. Go to **Apps**, remove the "Apps" filter, search for
   **"Public Job Application Portal"**, and click **Install**.
   (If you don't see it, click **Update Apps List** first — Odoo Technical
   settings must have Developer Mode on to see that option, or run
   `odoo-bin -u all -d your_database` from the command line.)

## How it works

| URL | Purpose |
|---|---|
| `/careers` | Public list of all open job positions |
| `/careers/apply/<job_id>` | Application form for one job |
| `/careers/apply/<job_id>/submit` | Form handler (POST only) |
| `/careers/apply/<job_id>/thankyou` | Confirmation page |

- Every **Job Position** form now has a **"Publish on Careers Portal?"**
  radio toggle at the bottom of the form (Recruitment app → Job Positions
  → open a job). Only jobs set to **Published** (and Active) appear on
  `/careers`.
- Submissions create an `hr.applicant` directly in that job's pipeline,
  first stage, exactly as if HR had entered it manually — CV attached,
  source tagged as **"Company Careers Portal"** for reporting.
- A hidden honeypot field filters basic spam bots; real visitors never
  see or fill it.
- CVs are restricted to PDF/DOC/DOCX, 5MB max.

## Using it with an external company website

Since this doesn't depend on the Website app, you have two simple options:

1. **Subdomain**: point `careers.yourcompany.com` at this Odoo instance
   and link to it from your main site's "Careers" nav item.
2. **Iframe embed**: embed `https://your-odoo-host/careers` inside an
   `<iframe>` on your existing external website if you want it to feel
   fully integrated on your current domain.

## Branding

- Go to **Settings → Users & Companies → Companies**, open your company,
  and you'll see a new **"Careers Portal Accent Color"** field (hex code,
  e.g. `#1A73E8`). This colors the buttons, links, and hover states on
  `/careers`. Defaults to `#714B67` if left blank.
- Your **company logo** (the same one used elsewhere in Odoo, under
  Company settings) is automatically shown at the top of every public
  careers page — no extra config needed.

## Job Description

- No separate portal description field — the portal reuses the
  standard **Job Summary** tab that already exists on every Job Position
  form (Recruitment app → Job Positions → open a job → **Job Summary**
  tab). Whatever you write there is what candidates see.
- This description renders in full on that job's `/careers/apply/<id>`
  page, and a short auto-generated plain-text preview (~160 characters)
  appears under the job title on the `/careers` listing page.
- The **Careers Portal** tab still exists on the form as a quick pointer
  to where the description and publish toggle live.

## Things to review before going live

- **HTTPS**: make sure your Odoo instance is served over HTTPS (CV
  uploads and personal data should never go over plain HTTP).
- **Incoming mail / notifications**: if you want HR to get notified per
  submission, add a Recruitment stage email template or an Odoo
  Automation Rule on `hr.applicant` create.
- **Spam**: the honeypot handles basic bots. For a public-facing site
  under real traffic, consider adding Google reCAPTCHA to the form for
  stronger protection (not included here to keep the module dependency-free).
- **GDPR / data retention**: confirm your recruitment data retention
  policy covers applicants who apply through this channel like any other.

## Files

```
hr_recruitment_public_apply/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   └── main.py              # public routes + form handling
├── models/
│   ├── __init__.py
│   └── hr_job.py             # adds "Publish on Careers Portal" toggle
├── views/
│   └── templates.xml         # the 3 public HTML pages (QWeb)
└── static/src/css/portal.css # styling
```
