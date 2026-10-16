/** @odoo-module **/
// Adds a "Request Stock" button next to "Close" on the warning shown when
// the Deduction Branch can not supply the products of a quotation (both the
// heads-up while editing and the error shown by Confirm).
//
// The server marks those warnings with two invisible characters at the end
// of the message (STOCK_WARNING_MARKER in models/sale_branch_stock.py), so
// the button also appears when the interface is translated.
// Everything is wrapped in try/catch: if anything differs in a future Odoo
// version the standard warning keeps working, it just has no extra button.
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { WarningDialog } from "@web/core/errors/error_dialogs";
import { router } from "@web/core/browser/router";

const MARKER = "\u2063\u2063";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

patch(WarningDialog.prototype, {
    setup() {
        super.setup(...arguments);
        // Never let this add-on break a warning dialog: if a service is
        // missing the dialog simply stays standard (no extra button).
        const safeService = (name) => {
            try {
                return useService(name);
            } catch (error) {
                console.warn("Request Stock button: service unavailable:", name);
                return null;
            }
        };
        this.abOrm = safeService("orm");
        this.abAction = safeService("action");
        this.abNotification = safeService("notification");
        onMounted(() => this.abAddRequestStockButton());
    },

    abAddRequestStockButton() {
        try {
            if (!(this.props.message || "").includes(MARKER)) {
                return;
            }
            if (!this.abOrm || !this.abAction) {
                return;
            }
            const dialogs = document.querySelectorAll(".o_dialog");
            const dialog = dialogs[dialogs.length - 1];
            const footer = dialog && dialog.querySelector(".modal-footer");
            if (!footer || footer.querySelector(".o_ab_request_stock")) {
                return;
            }
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-secondary o_ab_request_stock";
            button.innerHTML = '<i class="fa fa-truck me-1"></i>';
            button.appendChild(document.createTextNode(_t("Request Stock")));
            button.addEventListener("click", () => this.abRequestStock(button));
            footer.appendChild(button);
        } catch (error) {
            console.warn("Request Stock button not added", error);
        }
    },

    async abSaveFormIfDirty() {
        // The warning appears BEFORE the salesperson saves (e.g. right
        // after changing the branch), but the server builds the request
        // from the saved order, so save it first.
        const saveButton = document.querySelector(".o_form_button_save");
        if (!saveButton) {
            return;
        }
        saveButton.click();
        for (let i = 0; i < 40 && document.querySelector(".o_form_button_save"); i++) {
            await sleep(150);
        }
    },

    abCurrentOrderId() {
        const current = router.current || {};
        if (Number.isInteger(current.resId)) {
            return current.resId;
        }
        const controller = this.abAction.currentController;
        const props = (controller && controller.props) || {};
        return props.resModel === "sale.order" && Number.isInteger(props.resId)
            ? props.resId
            : false;
    },

    async abRequestStock(button) {
        button.disabled = true;
        try {
            await this.abSaveFormIfDirty();
            const orderId = this.abCurrentOrderId();
            if (!orderId) {
                this.abNotification.add(
                    _t("Please complete and save the quotation, then press Request Stock."),
                    { type: "warning" }
                );
                button.disabled = false;
                return;
            }
            const action = await this.abOrm.call("sale.order", "action_request_stock", [[orderId]]);
            this.props.close();
            await this.abAction.doAction(action);
        } catch (error) {
            button.disabled = false;
            throw error;
        }
    },
});
