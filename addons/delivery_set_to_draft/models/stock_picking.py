from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def action_set_to_draft_delivery(self):
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_("Only Inventory Managers can set a done delivery to draft."))
        for picking in self:
            if picking.state != 'done' or picking.picking_type_code != 'outgoing':
                raise UserError(_(
                    "%s is not a done delivery, only done outgoing deliveries can be set to draft.",
                    picking.name))
            picking._set_to_draft_and_revert()
        return True

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------
    def _set_to_draft_and_revert(self):
        self.ensure_one()
        moves = self.move_ids.filtered(lambda m: m.state == 'done')
        if not moves:
            raise UserError(_("%s has no done moves.", self.name))

        # A return already exists -> restoring stock again would double count.
        if moves.returned_move_ids.filtered(lambda m: m.state != 'cancel'):
            raise UserError(_(
                "%s already has a return. Cancel/handle the return first, "
                "otherwise the stock would be restored twice.", self.name))

        # 1. Stock: put quantities back in source, take them out of destination
        self._revert_quants(moves)

        # 2. Valuation: reverse layers + journal entries (or compute from cost)
        for move in moves:
            self._revert_move_valuation(move)

        # 3. Reset moves / lines to draft
        move_ids = tuple(moves.ids)
        self.env.cr.execute("DELETE FROM stock_move_line WHERE move_id IN %s", (move_ids,))
        self.env.cr.execute("UPDATE stock_move SET quantity = 0, picked = false WHERE id IN %s", (move_ids,))
        self.env.invalidate_all()
        moves = self.env['stock.move'].browse(move_ids)
        moves.write({'state': 'draft'})   # ORM write so picking state / SO delivered qty recompute
        self.write({'date_done': False})

        self.message_post(body=_(
            "Delivery set back to Draft by %s: stock restored and valuation reverted.",
            self.env.user.name))

    # ------------------------------------------------------------------
    # Stock quants
    # ------------------------------------------------------------------
    def _revert_quants(self, moves):
        Quant = self.env['stock.quant'].sudo()
        for ml in moves.move_line_ids:
            product = ml.product_id
            if not product.is_storable:
                continue
            qty = ml.quantity_product_uom
            if float_is_zero(qty, precision_rounding=product.uom_id.rounding):
                continue
            Quant._update_available_quantity(
                product, ml.location_id, qty,
                lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
            Quant._update_available_quantity(
                product, ml.location_dest_id, -qty,
                lot_id=ml.lot_id, package_id=ml.result_package_id, owner_id=ml.owner_id)

    # ------------------------------------------------------------------
    # Valuation
    # ------------------------------------------------------------------
    def _revert_move_valuation(self, move):
        product = move.product_id
        if not product.is_storable:
            return
        company = move.company_id
        currency = company.currency_id
        uom_rounding = product.uom_id.rounding
        today = fields.Date.context_today(self)

        qty = sum(move.move_line_ids.mapped('quantity_product_uom'))
        if float_is_zero(qty, precision_rounding=uom_rounding):
            return

        # outgoing (and later cost-adjustment) layers not yet handled
        layers = move.stock_valuation_layer_ids.filtered(
            lambda l: not l.draft_reversed and l.quantity <= 0)
        layer_qty = -sum(layers.mapped('quantity'))
        layer_value = -sum(layers.mapped('value'))

        if layers and layer_qty > 0 and not float_is_zero(layer_value, precision_rounding=currency.rounding):
            # Delivery had a cost: reuse the exact cost it was delivered at
            unit_cost = layer_value / layer_qty
            if float_compare(layer_qty, qty, precision_rounding=uom_rounding) == 0:
                value = layer_value
            else:
                value = currency.round(unit_cost * qty)
        else:
            # No cost / no valuation at delivery: qty x current product cost
            unit_cost = product.with_company(company).standard_price
            value = currency.round(unit_cost * qty)

        # reverse the journal entries of the original layers
        reversals = self.env['account.move']
        for am in layers.account_move_id:
            if am.state != 'posted':
                raise UserError(_(
                    "Journal entry %s linked to this delivery is not posted. "
                    "Post or cancel it first.", am.display_name))
            if self.env['account.move'].sudo().search_count([('reversed_entry_id', '=', am.id)]):
                continue
            rev = am._reverse_moves(
                [{'date': today,
                  'ref': _("Reversal of %(entry)s - %(picking)s set to draft",
                           entry=am.name, picking=self.name)}],
                cancel=False)
            rev.filtered(lambda m: m.state == 'draft')._post()
            reversals |= rev

        # counter layer (stock comes back in)
        counter = self.env['stock.valuation.layer'].sudo().create({
            'company_id': company.id,
            'product_id': product.id,
            'stock_move_id': move.id,
            'quantity': qty,
            'unit_cost': unit_cost,
            'value': value,
            'remaining_qty': qty,
            'remaining_value': value,
            'description': _("%s - set to draft", self.name),
            'draft_reversed': True,
        })
        layers.sudo().write({'draft_reversed': True})

        if reversals:
            counter.account_move_id = reversals[:1]
        elif (product.categ_id.with_company(company).property_valuation == 'real_time'
              and not currency.is_zero(value)):
            # nothing to reverse: book qty x cost with the category accounts
            counter.account_move_id = self._create_valuation_entry(move, qty, value, today)

    def _create_valuation_entry(self, move, qty, value, date):
        company = move.company_id
        product = move.product_id.with_company(company)
        categ = product.categ_id
        accounts = product.product_tmpl_id.get_product_accounts()
        valuation_acc = accounts.get('stock_valuation')
        counterpart_acc = accounts.get('stock_output')
        journal = categ.property_stock_journal
        if not (valuation_acc and counterpart_acc and journal):
            raise UserError(_(
                "Product category '%s' is missing its Stock Valuation account, "
                "Stock Output account or Stock Journal. Set them and try again.",
                categ.display_name))

        label = _("%(picking)s - %(product)s set to draft", picking=self.name, product=product.display_name)
        dr = value if value > 0 else 0.0
        cr = -value if value < 0 else 0.0
        entry = self.env['account.move'].sudo().with_company(company).create({
            'move_type': 'entry',
            'company_id': company.id,
            'journal_id': journal.id,
            'date': date,
            'ref': label,
            'stock_move_id': move.id,
            'line_ids': [
                # delivery was Dr Output / Cr Valuation -> reverse it
                (0, 0, {'name': label, 'account_id': valuation_acc.id,
                        'product_id': product.id, 'quantity': qty,
                        'debit': dr, 'credit': cr}),
                (0, 0, {'name': label, 'account_id': counterpart_acc.id,
                        'product_id': product.id, 'quantity': qty,
                        'debit': cr, 'credit': dr}),
            ],
        })
        entry._post()
        return entry
