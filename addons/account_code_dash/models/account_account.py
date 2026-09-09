# -*- coding: utf-8 -*-
import re

from odoo import api, models, _
from odoo.exceptions import ValidationError

# Core Odoo (18.0) uses: re.compile(r'^[A-Za-z0-9.]+$')
# We extend it to also allow a dash (-), so codes like "1000-07" are valid.
ACCOUNT_CODE_REGEX = re.compile(r'^[A-Za-z0-9.\-]+$')


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.constrains('code')
    def _check_account_code(self):
        """Override core's _check_account_code to also allow dashes ('-')
        in account codes, e.g. 1000-07.

        This fully replaces the core method (same name), so the original
        letters/digits/dot-only regex no longer applies.
        """
        for account in self:
            if account.code and not re.match(ACCOUNT_CODE_REGEX, account.code):
                raise ValidationError(_(
                    'The code "%(code)s" is not valid for account "%(name)s". '
                    'The account code can only contain letters, digits, dots (.) '
                    'and dashes (-).',
                    code=account.code,
                    name=account.name,
                ))
