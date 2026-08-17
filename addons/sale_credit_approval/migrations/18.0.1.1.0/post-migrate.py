# -*- coding: utf-8 -*-
"""Data migration for the "every order requires approval" change.

Before this version, `sale.order.requires_credit_approval` was computed
from `payment_term_id.requires_manager_approval`, so most existing orders
(anything not on a "Credit Sales"-type term) have it stored as False.

The compute method (see models/sale_order.py) is now a constant True for
every order. Odoo does NOT automatically re-run a stored compute for
existing rows just because its Python logic changed on upgrade - that only
happens for brand-new fields. So we correct the column directly here: any
DRAFT/SENT order that wasn't previously flagged now needs to be, so the
next confirm attempt correctly routes it into the approval workflow.
Already-confirmed orders are backfilled too, for data consistency, but that
has no behavioural effect since action_confirm() only checks this on
confirmation.

Also drops the now-unused account_payment_term.requires_manager_approval
column - the per-payment-term flag it backed no longer exists as a model
field (models/account_payment_term.py was removed in this version).
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE sale_order
        SET requires_credit_approval = TRUE
        WHERE requires_credit_approval IS DISTINCT FROM TRUE
    """)
    cr.execute("""
        ALTER TABLE account_payment_term
        DROP COLUMN IF EXISTS requires_manager_approval
    """)
