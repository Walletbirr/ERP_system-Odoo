/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";

const { useState, useRef, useExternalListener } = owl;

/**
 * Settings (cog) menu with an "Import records" entry, identical in behaviour to
 * the standard Odoo control-panel cog (opens the stock base_import wizard).
 *
 * @param {Object} params  { model: string, context?: Object }
 *   Static values, or pass functions returning them.
 */
export function useImportCog(params) {
    const action = useService("action");
    const ref = useRef("cog");
    const state = useState({ open: false });

    const close = () => {
        state.open = false;
    };
    useExternalListener(window, "click", (ev) => {
        if (state.open && !(ref.el && ref.el.contains(ev.target))) {
            close();
        }
    });
    useExternalListener(window, "keydown", (ev) => {
        if (ev.key === "Escape") {
            close();
        }
    });

    return {
        state,
        toggle(ev) {
            ev.stopPropagation();
            state.open = !state.open;
        },
        async importRecords() {
            close();
            const p = typeof params === "function" ? params() : params;
            await action.doAction({
                type: "ir.actions.client",
                tag: "import",
                params: { model: p.model, context: p.context || {} },
            });
        },
    };
}
