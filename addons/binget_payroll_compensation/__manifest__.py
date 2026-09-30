# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
{
    "name": "Payroll Compensation Defaults & Configuration",
    "summary": "Job Position compensation defaults (overridable per contract), "
    "department-based analytic accounts, and a single global Payroll "
    "configuration for the salary journal and fallback analytic account.",
    "version": "18.0.3.9.0",
    "category": "Human Resources/Payroll",
    "author": "Binget Holding",
    "license": "AGPL-3",
    "depends": ["hr_contract", "payroll", "payroll_account", "analytic"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_job_views.xml",
        "views/hr_department_views.xml",
        "views/hr_contract_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "binget_payroll_compensation/static/src/css/binget_payroll_compensation.css",
        ],
    },
    "installable": True,
    "application": False,
}
