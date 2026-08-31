# -*- coding: utf-8 -*-
"""
Runs after this module (including its own seed data in
data/hr_employee_education_config_data.xml) has finished loading, so
the ORM registry and the pre-populated config records already exist.

For every existing hr.employee.education row, look at the text value
that pre-migrate.py stashed away (x_old_education_level, ...), find or
create the matching hr.employee.education.* config record, and point
the new Many2one field at it. Finally drop the temp columns.
"""
from odoo import api, SUPERUSER_ID

OLD_TO_TEMP = {
    'education_level': 'x_old_education_level',
    'institution_name': 'x_old_institution_name',
    'field_of_study': 'x_old_field_of_study',
    'degree': 'x_old_degree',
}

FIELD_TO_MODEL = {
    'education_level': 'hr.employee.education.level',
    'institution_name': 'hr.employee.education.institution',
    'field_of_study': 'hr.employee.education.field',
    'degree': 'hr.employee.education.degree',
}

# The old education_level column held Selection keys, not human labels -
# map them onto the labels used by the seed data so existing records
# land on the same config record instead of creating "bachelor" next to
# "Bachelor's Degree".
LEVEL_KEY_LABELS = {
    'high_school': 'High School',
    'diploma': 'Diploma',
    'bachelor': "Bachelor's Degree",
    'master': "Master's Degree",
    'phd': 'Doctorate (PhD)',
    'other': 'Other',
}


def _existing_temp_columns(cr):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hr_employee_education'
          AND column_name IN %s
    """, (tuple(OLD_TO_TEMP.values()),))
    return {row[0] for row in cr.fetchall()}


def _get_or_create(env, model, name):
    name = (name or '').strip()
    if not name:
        return False
    record = env[model].with_context(active_test=False).search(
        [('name', '=ilike', name)], limit=1)
    if not record:
        record = env[model].create({'name': name})
    return record.id


def migrate(cr, version):
    if not version:
        return

    present_temp_columns = _existing_temp_columns(cr)
    if not present_temp_columns:
        # Fresh install, or already migrated in an earlier attempt -
        # nothing left to backfill.
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    select_cols = []
    for field, temp_column in OLD_TO_TEMP.items():
        select_cols.append(temp_column if temp_column in present_temp_columns
                            else "NULL AS %s" % temp_column)
    cr.execute(
        "SELECT id, %s FROM hr_employee_education" % ", ".join(select_cols)
    )
    rows = cr.fetchall()
    field_order = list(OLD_TO_TEMP.keys())

    for row in rows:
        rec_id = row[0]
        old_values = dict(zip(field_order, row[1:]))
        updates = {}

        for field, old_value in old_values.items():
            if not old_value:
                continue
            if field == 'education_level':
                old_value = LEVEL_KEY_LABELS.get(old_value, old_value)
            new_id = _get_or_create(env, FIELD_TO_MODEL[field], old_value)
            if new_id:
                updates[field] = new_id

        if updates:
            set_clause = ", ".join('"%s" = %%s' % k for k in updates)
            cr.execute(
                'UPDATE hr_employee_education SET %s WHERE id = %%s' % set_clause,
                list(updates.values()) + [rec_id],
            )

    for temp_column in present_temp_columns:
        cr.execute(
            'ALTER TABLE hr_employee_education DROP COLUMN IF EXISTS "%s"'
            % temp_column
        )
