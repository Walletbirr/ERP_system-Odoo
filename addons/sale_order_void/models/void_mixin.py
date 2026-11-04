from lxml import etree

from odoo import api, fields, models


class SaleVoidMixin(models.AbstractModel):
    _name = 'sale.void.mixin'
    _description = 'Void information'

    x_is_voided = fields.Boolean(
        string='Void', copy=False, readonly=True, index=True)
    x_void_reason = fields.Text(string='Void Reason', copy=False, readonly=True)
    x_void_date = fields.Datetime(string='Voided On', copy=False, readonly=True)
    x_void_user_id = fields.Many2one(
        'res.users', string='Voided By', copy=False, readonly=True)

    def _void_flag_values(self, reason):
        return {
            'x_is_voided': True,
            'x_void_reason': reason,
            'x_void_date': fields.Datetime.now(),
            'x_void_user_id': self.env.user.id,
        }

    @api.model
    def _void_patch_list_status(self, arch, success, info):
        """In list views, show Void instead of Cancelled for voided records.

        Done on the fly: every list that shows the status badge (whatever
        module defines it) gets a 'Display Status' badge column in its
        place. A list without that badge is left untouched.
        """
        for node in arch.xpath("//field[@name='state'][@widget='badge']"):
            hidden = node.get('column_invisible')
            if hidden in ('True', 'true', '1'):
                continue
            new = etree.Element('field', name='x_void_status',
                                widget='badge')
            new.set('string', node.get('string') or 'Status')
            if node.get('optional'):
                new.set('optional', node.get('optional'))
            if hidden:
                new.set('column_invisible', hidden)
            new.set('decoration-success', success)
            new.set('decoration-info', info)
            new.set('decoration-danger', "x_void_status == 'void'")
            node.set('column_invisible', 'True')
            node.addnext(new)
