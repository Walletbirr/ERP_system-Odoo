/** @odoo-module **/

/*
 * This registers OUR OWN dialog component to be used specifically for
 * AccessError, using Odoo's documented error_dialogs registry - this is
 * the officially supported extension point for this exact purpose
 * (see Odoo dev docs: "Error handling" / "Services" reference), rather
 * than patching an internal component's implementation directly, which
 * is what caused problems in earlier attempts.
 *
 * If this doesn't take effect, it likely means the lookup key
 * ("odoo.exceptions.AccessError") doesn't match what your Odoo build
 * actually sends - check the browser console for the real error name
 * shown there, and we can correct the key.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class AccessDeniedDialog extends Component {
    static template = "access_error_friendly_message.AccessDeniedDialog";
    static components = { Dialog };
    static props = ["*"];

    setup() {
        this.title = _t("Access Denied");
    }

    onClose() {
        this.props.close();
    }
}

registry.category("error_dialogs").add(
    "odoo.exceptions.AccessError",
    AccessDeniedDialog,
    { force: true }
);
