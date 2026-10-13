/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { SaleOrderLineListRenderer } from "@sale/js/sale_order_line_field/sale_order_line_field";

/**
 * Hide the auto-generated "Other Income" rows (any product flagged
 * "Hide From Invoice Lines Tab") from the Order Lines grid.
 *
 * The rows stay in the order_line field on purpose: the sale module's own JS
 * (product / combo configurator, optional products ...) addresses
 * `record.data.order_line` directly, so the field must not be renamed.
 * They still count towards totals and taxes and are printed normally.
 */
patch(SaleOrderLineListRenderer.prototype, {
    getRowClass(record) {
        const classNames = super.getRowClass(record);
        if (record.data.cim_hide_from_order_lines) {
            return `${classNames} d-none`;
        }
        return classNames;
    },
});
