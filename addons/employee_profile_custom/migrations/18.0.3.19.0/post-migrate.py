# -*- coding: utf-8 -*-
"""
18.0.3.19.0 adds the server-side tab stepper (profile_step /
profile_wizard_active) that replaces the old JS-based Previous/Next
widget.

`profile_wizard_active` defaults to True and `profile_step` defaults
to 'personal' for every row, including every employee that already
existed before this upgrade. Left alone, that would make the view
hide every tab except Personal Information for all of them the next
time someone opens an existing employee - a serious regression for
already-onboarded staff.

This script turns the wizard off for anyone who already existed prior
to this upgrade. Only genuinely new employees created from this point
forward go through the step-by-step gating.
"""


def migrate(cr, version):
    if not version:
        return

    # Raw SQL: cheap, and this table can be large; no need to route a
    # pure internal flag flip through the ORM (and no other logic here
    # needs an Environment).
    cr.execute("""
        UPDATE hr_employee
        SET profile_wizard_active = FALSE,
            profile_step = 'document'
    """)
