/** @odoo-module **/

/**
 * ENTER-KEY NAVIGATION ("Enter as Tab")
 *
 * In forms, dialogs and editable list rows, pressing Enter inside a
 * plain input moves focus to the next field instead of doing whatever
 * Odoo would do by default (e.g. saving the row and jumping to the
 * next one in a list).
 *
 * Rules:
 *  - Text-like inputs (char, integer, float, monetary, email, phone,
 *    url, password, date typed by hand, ...): Enter -> next field.
 *  - Dropdowns are left alone so the user can still pick from them:
 *      * <select> (selection fields): untouched.
 *      * Many2one / autocomplete: while its suggestion list is open,
 *        Enter picks the highlighted option as usual. Once the list
 *        is closed, the next Enter moves on.
 *      * Date/datetime: while the calendar popup is open, Enter is
 *        left to Odoo; once closed, the next Enter moves on.
 *  - <textarea> / html / contenteditable: untouched (Enter = new line).
 *  - Buttons and links: untouched (Enter = click).
 *  - Shift/Ctrl/Alt/Meta + Enter: untouched (shortcuts keep working).
 *  - Last field of a form / row: untouched, so Enter does whatever it
 *    did before (e.g. saves the list row). No surprise submit.
 *  - Chatter, search bar and control panel: untouched.
 *  - Any input can opt out with the attribute data-no-enter-nav.
 *
 * Deliberately pure DOM: a single document-level keydown listener with
 * NO Odoo imports, same safety idea as the rest of this module — if a
 * selector below is wrong, the worst case is "Enter behaves like stock
 * Odoo", never a broken page or a broken bundle.
 *
 * VERIFY (Odoo 18 markup, best-confidence guesses):
 *   ".o-autocomplete--input" / ".o-autocomplete--dropdown-menu"  many2one
 *   ".o_datetime_input" / ".o_datetime_picker"                   date popup
 *   ".o-mail-Chatter" / ".o-mail-Form-chatter"                   chatter
 * If a many2one or date field gets skipped past while its list is
 * still open, inspect it in devtools and send me the real class name.
 */

const SKIP_INPUT_TYPES = new Set([
    "hidden", "button", "submit", "reset", "image", "file", "range", "color",
]);
const NO_NAV_ZONES = ".o-mail-Chatter, .o-mail-Form-chatter, .o_searchview, .o_control_panel";

function isVisible(el) {
    if (!el.getClientRects().length) {
        return false;
    }
    return window.getComputedStyle(el).visibility !== "hidden";
}

/** Can focus legitimately land on this element as "the next field"? */
function isNavigable(el) {
    if (el.disabled || el.readOnly || el.tabIndex === -1) {
        return false;
    }
    if (el.tagName === "INPUT" && SKIP_INPUT_TYPES.has(el.type)) {
        return false;
    }
    if (el.closest(NO_NAV_ZONES) || el.closest("[data-no-enter-nav]")) {
        return false;
    }
    return isVisible(el);
}

/** Is a suggestion list / calendar currently open for this input? */
function hasOpenPopup(el) {
    const isAutocomplete =
        el.classList.contains("o-autocomplete--input") ||
        el.getAttribute("role") === "combobox";
    if (isAutocomplete) {
        if (el.getAttribute("aria-expanded") === "true") {
            return true;
        }
        if (document.querySelector(".o-autocomplete--dropdown-menu")) {
            return true;
        }
    }
    const isDate =
        el.classList.contains("o_datetime_input") ||
        el.closest(".o_field_date, .o_field_datetime, .o_field_daterange");
    if (isDate && document.querySelector(".o_datetime_picker")) {
        return true;
    }
    return false;
}

function findNextField(current) {
    // An editable list row wins over the form that contains it.
    const container =
        current.closest("tr.o_selected_row") ||
        current.closest(".o_form_view") ||
        null;
    if (!container) {
        return null;
    }
    const candidates = container.querySelectorAll("input, textarea, select");
    for (const candidate of candidates) {
        if (candidate === current || current.contains(candidate)) {
            continue;
        }
        const follows =
            current.compareDocumentPosition(candidate) & Node.DOCUMENT_POSITION_FOLLOWING;
        if (follows && isNavigable(candidate)) {
            return candidate;
        }
    }
    return null;
}

function onKeydown(ev) {
    if (
        ev.key !== "Enter" ||
        ev.isComposing || // IME (e.g. Amharic/Japanese) confirming a character
        ev.shiftKey || ev.ctrlKey || ev.altKey || ev.metaKey
    ) {
        return;
    }
    const el = ev.target;
    if (!(el instanceof HTMLInputElement) || SKIP_INPUT_TYPES.has(el.type)) {
        return; // textarea, select, button, contenteditable, ... -> untouched
    }
    if (el.closest(NO_NAV_ZONES) || el.closest("[data-no-enter-nav]")) {
        return;
    }
    if (hasOpenPopup(el)) {
        return; // let Odoo select the highlighted dropdown option
    }
    const next = findNextField(el);
    if (!next) {
        return; // last field: keep Odoo's default Enter behavior
    }
    ev.preventDefault();
    ev.stopImmediatePropagation();
    next.focus();
    if (typeof next.select === "function" && next.tagName === "INPUT") {
        try {
            next.select(); // highlight existing value so typing replaces it
        } catch {
            // some input types (e.g. number) don't support select(); ignore
        }
    }
}

// Capture phase so we run before Odoo's own row/list Enter handling.
document.addEventListener("keydown", onKeydown, true);
