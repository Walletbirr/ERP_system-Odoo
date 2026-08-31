# -*- coding: utf-8 -*-
"""
education_level / institution_name / field_of_study / degree on
hr.employee.education are changing from Selection/Char (text columns)
to Many2one (integer columns).

Odoo's automatic schema sync tries to convert the existing column
in place (``ALTER TABLE ... USING col::integer``), which fails as soon
as the column holds any real text ('bachelor', 'other', 'Addis Ababa
University', ...) because none of that casts to an integer.

Renaming the old columns out of the way here (pre-migrate, i.e. before
_auto_init runs for this module) means Odoo just creates brand new
empty integer columns under the original names instead of trying to
convert anything. post-migrate.py then reads the renamed columns back
and populates proper hr.employee.education.* records + links them.
"""

OLD_TO_TEMP = {
    'education_level': 'x_old_education_level',
    'institution_name': 'x_old_institution_name',
    'field_of_study': 'x_old_field_of_study',
    'degree': 'x_old_degree',
}


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'hr_employee_education'
          AND column_name IN %s
    """, (tuple(OLD_TO_TEMP.keys()),))
    existing = dict(cr.fetchall())

    for column, data_type in existing.items():
        if data_type == 'integer':
            # Already migrated (or a fresh install created it directly
            # as the new Many2one type) - nothing to rename.
            continue
        temp_column = OLD_TO_TEMP[column]
        cr.execute(
            'ALTER TABLE hr_employee_education RENAME COLUMN "%s" TO "%s"'
            % (column, temp_column)
        )
