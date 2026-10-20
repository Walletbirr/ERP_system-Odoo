/** @odoo-module **/
// Payment Proofs tab on the Sales Order (salesperson side):
//  1. Auto-save: after the salesperson uploads / types in a proof line,
//     clicking anywhere outside the Payment Proofs list saves the order
//     (no trip to the Save button). Lines stay editable until Submit.
//  2. Submit: the line's Submit button saves the order first (a line that
//     was just added has no id yet and Odoo refuses to run a button on it:
//     "Please save your changes first"), then submits that line.
//
// Uses the form's own record (save / reload) and the standard ORM call, the
// same thing a normal button does. Only active on the sale.order form and
// only for buttons / lines of the payment proof list.
import { patch } from "@web/core/utils/patch";
import { useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { FormController } from "@web/views/form/form_controller";

const FIELD = '.o_field_widget[name="payment_proof_ids"]';
const SKIP_CLICK_ON =
    ".o_form_button_cancel, .o_form_button_save, .modal, .o_dialog, .o_popover, .dropdown-menu";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.props.resModel !== "sale.order") {
            return;
        }
        this.abOrm = useService("orm");
        this.abNotification = useService("notification");
        this.abBusy = false;
        const onClick = (ev) => this.abOnClick(ev);
        const onPointerDown = (ev) => this.abOnPointerDown(ev);
        useEffect(
            (el) => {
                if (!el) {
                    return;
                }
                el.addEventListener("click", onClick, true);
                document.addEventListener("pointerdown", onPointerDown, true);
                return () => {
                    el.removeEventListener("click", onClick, true);
                    document.removeEventListener("pointerdown", onPointerDown, true);
                };
            },
            () => [this.rootRef && this.rootRef.el]
        );
    },

    abProofField() {
        return this.rootRef && this.rootRef.el && this.rootRef.el.querySelector(FIELD);
    },

    abIsEditingProof() {
        const field = this.abProofField();
        return !!(field && field.querySelector(".o_selected_row"));
    },

    /** Click anywhere outside the proof list while a line is being edited:
     * save the order, committing the line. */
    async abOnPointerDown(ev) {
        try {
            if (this.abBusy || !this.abIsEditingProof()) {
                return;
            }
            const target = ev.target;
            const field = this.abProofField();
            if (!target.closest || field.contains(target) || target.closest(SKIP_CLICK_ON)) {
                return;
            }
            this.abBusy = true;
            try {
                await this.model.root.save();
            } finally {
                this.abBusy = false;
            }
        } catch (error) {
            this.abBusy = false;
            console.warn("Payment proof auto-save skipped", error);
        }
    },

    async abOnClick(ev) {
        const button = ev.target.closest && ev.target.closest(".o_ab_submit_proof");
        if (!button) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        ev.stopImmediatePropagation();
        if (this.abBusy) {
            return;
        }
        this.abBusy = true;
        try {
            const root = this.model.root;
            const field = this.abProofField();
            const row = button.closest(".o_data_row");
            const index = field && row
                ? [...field.querySelectorAll(".o_data_row")].indexOf(row)
                : -1;
            // Saves the order, committing the line being edited first.
            const saved = await root.save();
            if (saved === false) {
                return;
            }
            const record = index >= 0 ? root.data.payment_proof_ids.records[index] : null;
            if (record && record.resId) {
                await this.abOrm.call("sale.order.payment.proof", "action_submit", [[record.resId]]);
            } else {
                await this.abOrm.call("sale.order", "action_submit_payment_proofs", [[root.resId]]);
            }
            await this.model.load();
            this.abNotification.add(_t("Payment proof submitted to Accounting."), {
                type: "success",
            });
        } finally {
            this.abBusy = false;
        }
    },
});
