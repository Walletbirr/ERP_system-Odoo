# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    """Extends the payslip batch to add a one-click confirm-all action."""
    _inherit = 'hr.payslip.run'

    def action_confirm_all_payslips(self):
        """Compute (if needed) and confirm every payslip in this batch
        that isn't already confirmed or cancelled. Payslips that fail
        are skipped and reported at the end instead of stopping the
        whole batch."""
        self.ensure_one()

        slips_to_confirm = self.slip_ids.filtered(
            lambda slip: slip.state not in ('done', 'cancel')
        )

        if not slips_to_confirm:
            raise UserError(_(
                "There are no payslips left to confirm in this batch "
                "(they may already be confirmed or cancelled)."
            ))

        failed = []
        for slip in slips_to_confirm:
            try:
                # action_payslip_done() computes the sheet internally
                # before confirming, so no separate compute step is needed.
                slip.action_payslip_done()
            except Exception as e:
                failed.append((slip.number or slip.name or str(slip.id), str(e)))

        if failed:
            details = "\n".join(
                "- %s: %s" % (ref, msg) for ref, msg in failed
            )
            raise UserError(_(
                "%(count)s payslip(s) were confirmed. %(failed_count)s could "
                "not be confirmed:\n%(details)s"
            ) % {
                'count': len(slips_to_confirm) - len(failed),
                'failed_count': len(failed),
                'details': details,
            })

        return True
