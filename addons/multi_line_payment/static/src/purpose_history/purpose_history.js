/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { useRef, useState } from "@odoo/owl";

/**
 * Char field that shows the user's previous values (history) in a small panel
 * under the input when the field is clicked. Click an entry to use it, click
 * the x to remove it from the history.
 */
export class PurposeHistoryField extends CharField {
    static template = "multi_line_payment.PurposeHistoryField";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.wrapper = useRef("wrapper");
        this.historyState = useState({ open: false, loaded: false, items: [], query: "" });
    }

    get filteredItems() {
        const query = (this.historyState.query || "").trim().toLowerCase();
        const items = this.historyState.items;
        if (!query) {
            return items;
        }
        return items.filter(
            (item) => item.name.toLowerCase().includes(query) && item.name.toLowerCase() !== query
        );
    }

    async loadHistory() {
        try {
            this.historyState.items = await this.orm.searchRead(
                "payment.purpose.history",
                [],
                ["name"],
                { limit: 12, order: "last_used desc, id desc" }
            );
        } catch {
            this.historyState.items = [];
        }
        this.historyState.loaded = true;
    }

    async onFocusIn() {
        if (this.props.readonly) {
            return;
        }
        this.historyState.query = this.input.el ? this.input.el.value : "";
        this.historyState.open = true;
        await this.loadHistory();
    }

    onFocusOut(ev) {
        const wrapper = this.wrapper.el;
        if (wrapper && ev.relatedTarget && wrapper.contains(ev.relatedTarget)) {
            return;
        }
        this.historyState.open = false;
    }

    onInput(ev) {
        this.historyState.query = ev.target.value;
    }

    onKeydown(ev) {
        if (ev.key === "Escape" && this.historyState.open) {
            this.historyState.open = false;
            ev.stopPropagation();
        }
    }

    async onSelect(item) {
        if (this.input.el) {
            this.input.el.value = item.name;
        }
        await this.props.record.update({ [this.props.name]: item.name });
        this.historyState.open = false;
    }

    async onRemove(item) {
        this.historyState.items = this.historyState.items.filter((i) => i.id !== item.id);
        try {
            await this.orm.unlink("payment.purpose.history", [item.id]);
        } catch {
            await this.loadHistory();
        }
    }

    async onClearAll() {
        this.historyState.items = [];
        try {
            await this.orm.call("payment.purpose.history", "clear_all", []);
        } catch {
            await this.loadHistory();
        }
    }
}

registry.category("fields").add("purpose_history", {
    ...charField,
    component: PurposeHistoryField,
    displayName: "Purpose with history",
});
