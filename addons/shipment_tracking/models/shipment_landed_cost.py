# /custom_addons/shipment_tracking/models/shipment_landed_cost.py
#
# PURPOSE
# ───────
# Bidirectional link between your custom Shipment Tracking records and
# Odoo's native stock.landed.cost (Inventory ▸ Operations ▸ Landed Costs).
#
# FROM the Inventory Landed Cost form  →  pick the Shipment in the new
#   "Shipment Reference" field.
#
# FROM the Shipment form               →  a "Landed Costs" stat button
#   shows the count and opens all linked stock.landed.cost records.
#
# HOW IT WORKS
# ────────────
# 1. ShipmentLandedCostInherit   — adds `shipment_id` Many2one on
#    stock.landed.cost (one landed cost belongs to one shipment).
#    When `shipment_id` is set/changed, `_onchange_shipment_id` fires
#    and auto-fills the cost_lines from shipment.cost records.
#
# 2. ShipmentTrackingLandedCost  — adds `landed_cost_ids` computed
#    One2many on shipment.tracking so the stat button can count and
#    open all linked stock.landed.cost records.

from odoo import models, fields, api, _


# ── Mapping: shipment.cost stage name → LC split method ──────────────────────
# Matched by keyword against the Cost Stage's name (case-insensitive),
# since Cost Stages are now user-configurable records instead of a fixed
# Selection list. Adjust these keywords to match your stage names.
_SPLIT_METHOD_DEFAULT = 'by_current_cost_price'
_STAGE_KEYWORD_TO_SPLIT = {
    'sea freight':      'by_weight',
    'custom':           'by_current_cost_price',
    'duty':             'by_current_cost_price',
    'local transport':  'by_current_cost_price',
}


def _split_method_for_stage(stage_name):
    name = (stage_name or '').lower()
    for keyword, method in _STAGE_KEYWORD_TO_SPLIT.items():
        if keyword in name:
            return method
    return _SPLIT_METHOD_DEFAULT


class ShipmentLandedCostInherit(models.Model):
    """
    Extends Odoo's native stock.landed.cost with a link back to the
    Shipment Tracking record that triggered this landed cost entry.

    Setting `shipment_id` on the Landed Cost form will:
      1. Store the link so the shipment's stat button shows this LC.
      2. Auto-populate cost_lines from the shipment's shipment.cost records
         (you can still edit/remove those lines afterwards).
    """
    _inherit = 'stock.landed.cost'

    shipment_id = fields.Many2one(
        comodel_name='shipment.tracking',
        string='Shipment Reference',
        tracking=True,
        ondelete='set null',
        index=True,
        help=(
            'Link this Landed Cost entry to an Import Shipment record. '
            'Once set, the shipment\'s "Landed Costs" smart button will '
            'include this entry in its count and list. '
            'The Additional Costs tab will be pre-filled from the shipment\'s costs.'
        ),
    )

    # ── Onchange: auto-fill cost_lines from shipment costs ────────────────────
    @api.onchange('shipment_id')
    def _onchange_shipment_id(self):
        """
        When the user picks a Shipment, auto-populate the Additional Costs
        (cost_lines) with the shipment's cost entries (shipment.cost).

        Each shipment.cost becomes one stock.landed.cost.line entry with:
          - product_id  : the cost's product (if set) or a fallback service product
          - name        : the shipment cost display_name
          - account_id  : the cost's fee_account_id (if set)
          - split_method: mapped from the cost stage
          - price_unit  : total_amount (in company currency) or amount
        """
        if not self.shipment_id:
            return

        shipment = self.shipment_id

        # Gather shipment costs that have an amount
        cost_records = shipment.cost_ids.filtered(lambda c: c.total_amount > 0)

        if not cost_records:
            return

        # Try to find a generic "Landed Cost" service product to use as fallback
        # (Odoo requires a product on each cost line)
        LandedCostProduct = self.env['product.product'].search([
            ('type', '=', 'service'),
            ('name', 'ilike', 'landed cost'),
        ], limit=1)

        new_lines = []
        for sc in cost_records:
            # Determine the product: use a dedicated service product per stage
            # or fall back to any service product named "Landed Cost"
            product = self._get_landed_cost_product(sc) or LandedCostProduct

            if not product:
                # Skip lines where we cannot determine a product — Odoo requires it
                continue

            split_method = _split_method_for_stage(sc.stage_id.name)

            line_vals = {
                'product_id': product.id,
                'name': sc.display_name or sc.stage_id.name,
                'split_method': split_method,
                'price_unit': sc.amount_company or sc.total_amount or sc.amount,
            }

            # Link account if available
            if sc.fee_account_id:
                line_vals['account_id'] = sc.fee_account_id.id

            new_lines.append((0, 0, line_vals))

        if new_lines:
            self.cost_lines = [(5, 0, 0)] + new_lines  # clear existing, add new

    # ── Helper: resolve a service product for a given shipment cost stage ─────
    def _get_landed_cost_product(self, shipment_cost):
        """
        Try to find a service product that matches the shipment cost stage.
        Searches by name keywords so you don't need to hard-code product IDs.
        Override this method to apply your own product-resolution logic.
        """
        Product = self.env['product.product']
        stage_name = (shipment_cost.stage_id.name or '').lower()

        stage_keywords_map = [
            ('sea freight',     ['sea freight', 'ocean freight', 'freight']),
            ('custom',          ['customs', 'clearance', 'duty']),
            ('duty',            ['customs', 'clearance', 'duty']),
            ('local transport', ['local freight', 'local transport', 'transport']),
        ]

        keywords = ['landed cost', 'shipment cost']
        for needle, kws in stage_keywords_map:
            if needle in stage_name:
                keywords = kws
                break

        for kw in keywords:
            product = Product.search([
                ('type', '=', 'service'),
                ('name', 'ilike', kw),
            ], limit=1)
            if product:
                return product

        # Final fallback: any service product
        return Product.search([('type', '=', 'service')], limit=1)

    # ── Button: re-sync cost lines from shipment on demand ────────────────────
    def action_sync_costs_from_shipment(self):
        """
        Manual re-sync button: re-reads the shipment costs and rebuilds
        cost_lines. Useful after costs are updated on the shipment side.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise models.ValidationError(
                _('Cannot sync costs on a validated Landed Cost. Reset to Draft first.')
            )
        # Trigger onchange manually
        self._onchange_shipment_id()


class ShipmentTrackingLandedCost(models.Model):
    """
    Adds landed-cost awareness to shipment.tracking:
      • landed_cost_ids  — virtual One2many (not stored) so the stat button
                           can open the filtered act_window.
      • landed_cost_count — stored Integer for the badge on the stat button.
      • action_view_landed_costs() — opens the filtered landed cost list.
    """
    _inherit = 'shipment.tracking'

    # ── Reverse relation ──────────────────────────────────────────────────────
    landed_cost_ids = fields.One2many(
        comodel_name='stock.landed.cost',
        inverse_name='shipment_id',
        string='Landed Costs',
        readonly=True,
    )

    landed_cost_count = fields.Integer(
        string='Landed Costs',
        compute='_compute_landed_cost_count',
        store=True,
        help='Number of Inventory Landed Cost entries linked to this shipment.',
    )

    # ── Compute ───────────────────────────────────────────────────────────────
    @api.depends('landed_cost_ids')
    def _compute_landed_cost_count(self):
        for rec in self:
            rec.landed_cost_count = len(rec.landed_cost_ids)

    # ── Stat button action ────────────────────────────────────────────────────
    def action_view_landed_costs(self):
        """
        Opens the list (or form if only one) of stock.landed.cost records
        linked to this shipment. Called by the stat button in the view.
        """
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Landed Costs – %s') % self.reference,
            'res_model': 'stock.landed.cost',
            'view_mode': 'list,form',
            'domain': [('shipment_id', '=', self.id)],
            'context': {
                # Pre-fill the shipment when the user creates a new LC from here
                'default_shipment_id': self.id,
            },
        }
        # If there is exactly one record, open the form directly
        if self.landed_cost_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.landed_cost_ids[0].id
        return action
