# Part of Binget Holding customizations. See LICENSE file for full copyright
# and licensing details.
#
# This runs once, automatically, the moment this module is upgraded past
# 18.0.2.0.0. It copies whatever was already saved in the old fixed
# transport/position/house allowance fields (on both Job Position and
# Contract) into the new dynamic allowance-line records, so nothing you've
# already entered gets lost when the fields disappear from the form.
#
# It reads the old values via raw SQL rather than the ORM, since by the
# time this script runs the ORM no longer knows those fields exist (they
# were removed from the Python model) - but the database columns
# themselves are still physically present until Odoo's schema cleanup
# eventually drops them, so this is safe to read directly.

from odoo import SUPERUSER_ID, api


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    rule_by_code = {
        code: env["hr.salary.rule"].search([("code", "=", code)], limit=1)
        for code in ("TRANS", "POS", "HOUSE")
    }

    job_field_map = {
        "default_transport_allowance": "TRANS",
        "default_position_allowance": "POS",
        "default_house_allowance": "HOUSE",
    }
    for column, code in job_field_map.items():
        rule = rule_by_code.get(code)
        if not rule or not _column_exists(cr, "hr_job", column):
            continue
        cr.execute(
            f"SELECT id, {column} FROM hr_job "
            f"WHERE {column} IS NOT NULL AND {column} != 0"
        )
        for job_id, amount in cr.fetchall():
            env["hr.job.allowance.line"].create(
                {"job_id": job_id, "rule_id": rule.id, "amount": amount}
            )

    contract_field_map = {
        "transport_allowance": "TRANS",
        "position_allowance": "POS",
        "house_allowance": "HOUSE",
    }
    for column, code in contract_field_map.items():
        rule = rule_by_code.get(code)
        if not rule or not _column_exists(cr, "hr_contract", column):
            continue
        cr.execute(
            f"SELECT id, {column} FROM hr_contract "
            f"WHERE {column} IS NOT NULL AND {column} != 0"
        )
        for contract_id, amount in cr.fetchall():
            env["hr.contract.allowance.line"].create(
                {
                    "contract_id": contract_id,
                    "rule_id": rule.id,
                    "amount": amount,
                }
            )
