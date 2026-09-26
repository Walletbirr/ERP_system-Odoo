# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import UserError


class HrContract(models.Model):
    _inherit = "hr.contract"

    # ------------------------------------------------------------------
    # "Make contract Readonly" - enforced here, not only via a view
    # attribute. A view-only readonly can still be bypassed (XML-RPC,
    # a different view, an import) - blocking it in write() is what
    # actually guarantees it. `state` itself is deliberately excluded,
    # so the contract can still move Draft -> Running -> Expired /
    # Cancelled normally; only the *content* fields lock once Running.
    # ------------------------------------------------------------------
    def write(self, vals):
        for contract in self:
            if contract.state == "open":
                blocked = set(vals.keys()) - {"state"}
                if blocked:
                    raise UserError(_(
                        "%(employee)s's contract is Running and is now "
                        "read-only. Only its status can still be changed "
                        "from here."
                    ) % {"employee": contract.employee_id.name})
        return super().write(vals)
