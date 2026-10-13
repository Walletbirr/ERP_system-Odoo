# -*- coding: utf-8 -*-

SERVICE_LABEL = "Other Income"


def rename_service_charge_product(env):
    """Label only: show the auto-generated balancing line as "Other Income".

    The product itself (custom_invoice_management.product_service_charge),
    its income account and all the logic stay exactly as they were.
    """
    product = env.ref(
        'custom_invoice_management.product_service_charge', raise_if_not_found=False
    )
    if not product:
        return
    if product.name != SERVICE_LABEL:
        product.write({'name': SERVICE_LABEL})
    # Quotations that are still open: refresh the label of their existing
    # lines too. Confirmed orders / posted invoices are history, left alone.
    lines = env['sale.order.line'].with_context(cim_skip_auto_balance=True).search([
        ('product_id', '=', product.id),
        ('order_id.state', 'in', ('draft', 'sent')),
        ('name', '!=', SERVICE_LABEL),
    ])
    if lines:
        lines.write({'name': SERVICE_LABEL})


def post_init_hook(env):
    rename_service_charge_product(env)
