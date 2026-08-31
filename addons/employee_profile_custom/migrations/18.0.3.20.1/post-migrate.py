# -*- coding: utf-8 -*-
"""
gender_id / marital_status_id / blood_type_id are brand new columns, so
no risky in-place type conversion happens here (unlike the earlier
Education migration) - this script only needs to backfill them for
employees that already have data.

- gender / marital are still real fields on hr.employee (untouched),
  so they're read straight through the ORM.
- blood_type was removed as a field entirely; its old column may still
  be sitting in the database unused, so it's read with raw SQL.
"""
from odoo import api, SUPERUSER_ID

GENDER_LABELS = {'male': 'Male', 'female': 'Female', 'other': 'Other'}
MARITAL_LABELS = {
    'single': 'Single', 'married': 'Married', 'cohabitant': 'Cohabitant',
    'widower': 'Widowed', 'divorced': 'Divorced',
}
BLOOD_TYPE_LABELS = {'a': 'A', 'b': 'B', 'ab': 'AB', 'o': 'O'}


def _get_or_create(env, model, name):
    name = (name or '').strip()
    if not name:
        return False
    record = env[model].with_context(active_test=False).search(
        [('name', '=ilike', name)], limit=1)
    if not record:
        record = env[model].create({'name': name})
    return record.id


def _column_exists(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    # ---------------- Gender & Marital Status (still real ORM fields) ----------------
    employees = env['hr.employee'].with_context(active_test=False).search([])
    gender_cache = {}
    marital_cache = {}
    for employee in employees:
        vals = {}
        if employee.gender and not employee.gender_id:
            label = GENDER_LABELS.get(employee.gender, employee.gender)
            if label not in gender_cache:
                gender_cache[label] = _get_or_create(env, 'hr.employee.gender', label)
            if gender_cache[label]:
                vals['gender_id'] = gender_cache[label]
        if employee.marital and not employee.marital_status_id:
            label = MARITAL_LABELS.get(employee.marital, employee.marital)
            if label not in marital_cache:
                marital_cache[label] = _get_or_create(env, 'hr.employee.marital.status', label)
            if marital_cache[label]:
                vals['marital_status_id'] = marital_cache[label]
        if vals:
            employee.write(vals)

    # ---------------- Blood Type (old column, field no longer declared) ----------------
    if _column_exists(cr, 'hr_employee', 'blood_type'):
        cr.execute('SELECT id, blood_type FROM hr_employee WHERE blood_type IS NOT NULL')
        blood_cache = {}
        for emp_id, old_value in cr.fetchall():
            if not old_value:
                continue
            label = BLOOD_TYPE_LABELS.get(old_value, old_value)
            if label not in blood_cache:
                blood_cache[label] = _get_or_create(env, 'hr.employee.blood.type', label)
            if blood_cache[label]:
                cr.execute(
                    'UPDATE hr_employee SET blood_type_id = %s WHERE id = %s',
                    (blood_cache[label], emp_id),
                )
        cr.execute('ALTER TABLE hr_employee DROP COLUMN IF EXISTS blood_type')

    # The old 'blood_type' field is no longer declared in hr_employee.py, but
    # the registry may still hold a stale ir.model.fields record for it (state
    # 'base', reflecting a field that used to be defined in code). If that
    # record survives an incomplete/older upgrade, view rendering later fails
    # with: "hr.employee"."blood_type" field is undefined.
    # Remove it explicitly here so the cleanup is safe, repeatable, and
    # doesn't rely on a manual deletion in production.
    stale_field = env['ir.model.fields'].search([
        ('model', '=', 'hr.employee'),
        ('name', '=', 'blood_type'),
    ])
    if stale_field:
        stale_field.unlink()
