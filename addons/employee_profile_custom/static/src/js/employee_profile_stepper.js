/** @odoo-module **/

import { Component, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { evaluateExpr } from "@web/core/py_js/py";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * Previous / Next stepper bar shown at the bottom of every tab of the
 * Employee Profile notebook, so the form behaves like a guided,
 * step-by-step wizard instead of a flat set of tabs the user can jump
 * around in freely.
 *
 * - "Previous" always just switches tabs, no validation needed going
 *   backwards.
 * - "Next" first checks the required fields declared for the *current*
 *   tab (passed in through the `options` widget attribute); if any of
 *   them are empty, it blocks navigation, shows a toast telling the
 *   user exactly what's missing, and highlights those fields instead
 *   of silently doing nothing.
 * - Clicking a tab header directly (bypassing the Next button
 *   entirely) is guarded the same way: each instance of this widget
 *   watches the nav-tabs bar, and while its OWN page is the one
 *   currently showing, it intercepts clicks on any other tab header
 *   and runs the exact same required-field check before allowing the
 *   native tab switch to happen. Only one instance's page can be
 *   active at a time, so exactly one of them ever acts on a given
 *   click - the rest bail out immediately.
 *
 * Tabs are matched by their visible label (the <page string="..."/>)
 * rather than by index, so this keeps working even if tabs are
 * reordered, added or removed later - only the `options` on the
 * widget that references a moved tab would need updating.
 */
export class ProfileStepNav extends Component {
    static template = "employee_profile_custom.ProfileStepNav";
    static props = {
        ...standardWidgetProps,
        // Owl validates every prop a component receives against its static
        // `props` schema - anything returned by extractProps() below MUST
        // be declared here too, or Owl silently rejects the whole
        // component (it never mounts, no error visible in the UI).
        options: { type: Object, optional: true },
    };

    setup() {
        this.notification = useService("notification");
        this.rootRef = useRef("profileStepNavRoot");
        this._onNavTabsClickCapture = this._onNavTabsClickCapture.bind(this);
        onMounted(() => this._bindTabInterceptor());
        onWillUnmount(() => this._unbindTabInterceptor());
    }

    get options() {
        return this._options || (this._options = this._parseOptions());
    }

    _parseOptions() {
        // extractProps (below) already parses the `options` XML attribute
        // into a plain object for us. This is defensive only, in case a
        // future refactor passes the raw string through unparsed.
        const opts = this.props.options;
        if (!opts) {
            return {};
        }
        if (typeof opts === "string") {
            try {
                return evaluateExpr(opts) || {};
            } catch {
                return {};
            }
        }
        return opts;
    }

    get prevLabel() {
        return this.options.prev || null;
    }

    get nextLabel() {
        return this.options.next || null;
    }

    get requiredFields() {
        return this.options.required || [];
    }

    _getProfileRoot() {
        const el = this.rootRef.el;
        return el ? el.closest(".o_employee_profile_root") : null;
    }

    _getNavTabs() {
        const root = this._getProfileRoot();
        return root ? root.querySelector(".o_notebook .nav-tabs") : null;
    }

    // The tab-pane that contains THIS widget instance - i.e. this
    // instance's own page. Used to tell whether this instance's tab is
    // the one currently showing.
    _getOwnPane() {
        const el = this.rootRef.el;
        return el ? el.closest(".tab-pane") : null;
    }

    _isOwnPaneActive() {
        const pane = this._getOwnPane();
        if (!pane) {
            return false;
        }
        // Class-name-agnostic: whichever pane is actually visible on
        // screen right now is the active one, regardless of exactly
        // which CSS classes this Odoo version's Notebook happens to use.
        return pane.offsetParent !== null && pane.getClientRects().length > 0;
    }

    _clickTab(label, { skipValidation = false } = {}) {
        const root = this._getProfileRoot();
        if (!root || !label) {
            return;
        }
        // NOTE: .nav-tabs is nested one level deeper than .o_notebook (inside
        // .o_notebook_headers), so it must NOT be matched as a *direct*
        // child of .o_notebook - that combinator previously matched
        // nothing, silently breaking every Previous/Next click.
        const links = root.querySelectorAll(".o_notebook .nav-tabs .nav-link");
        for (const link of links) {
            if (link.textContent.trim() === label) {
                if (skipValidation) {
                    // Mark this exact click as pre-validated (or
                    // intentionally unvalidated, e.g. Previous) so our own
                    // capture-phase interceptor - which will also see this
                    // synthetic click - lets it straight through instead
                    // of re-checking required fields a second time.
                    link.dataset.profileStepSkipValidation = "1";
                }
                link.click();
                root.scrollIntoView({ behavior: "smooth", block: "start" });
                return;
            }
        }
    }

    _clearInvalidHighlights() {
        const root = this._getProfileRoot();
        if (!root) {
            return;
        }
        root.querySelectorAll(".o_employee_profile_row_invalid").forEach((rowEl) => {
            rowEl.classList.remove("o_employee_profile_row_invalid");
        });
    }

    _highlightMissing(fieldNames) {
        const root = this._getProfileRoot();
        if (!root) {
            return;
        }
        for (const name of fieldNames) {
            const fieldEl = root.querySelector(
                `.tab-pane.active [name="${CSS.escape(name)}"]`
            );
            const rowEl = fieldEl && fieldEl.closest(".o_employee_profile_row");
            if (rowEl) {
                rowEl.classList.add("o_employee_profile_row_invalid");
            }
        }
    }

    _isEmptyValue(value) {
        if (value === false || value === undefined || value === null || value === "") {
            return true;
        }
        // Plain arrays (rare, but some widgets still expose one) and the
        // Many2one [id, display_name] tuple.
        if (Array.isArray(value)) {
            return value.length === 0;
        }
        // One2many / Many2many fields are exposed as a "StaticList"-like
        // object on record.data, not a plain array - length lives on
        // `.records` (or, depending on version, `.currentIds`).
        if (value && typeof value === "object") {
            if (Array.isArray(value.records)) {
                return value.records.length === 0;
            }
            if (Array.isArray(value.currentIds)) {
                return value.currentIds.length === 0;
            }
        }
        return false;
    }

    // Shared by both the Next button and the tab-header interceptor:
    // checks this tab's own required fields against the current record
    // state. Returns {valid, missing, missingNames}.
    _validateRequired() {
        const record = this.props.record;
        const missing = [];
        const missingNames = [];
        for (const field of this.requiredFields) {
            const value = record && record.data ? record.data[field.name] : undefined;
            if (this._isEmptyValue(value)) {
                missing.push(field.label || field.name);
                missingNames.push(field.name);
            }
        }
        return { valid: missing.length === 0, missing, missingNames };
    }

    _blockWithMissingFieldsNotice(missing, missingNames) {
        this._highlightMissing(missingNames);
        this.notification.add(
            `Please fill in the required field(s) before continuing: ${missing.join(", ")}`,
            { type: "danger", title: "Missing information" }
        );
    }

    onPrev() {
        this._clearInvalidHighlights();
        // Going backward never needs validation.
        this._clickTab(this.prevLabel, { skipValidation: true });
    }

    onNext() {
        this._clearInvalidHighlights();
        const { valid, missing, missingNames } = this._validateRequired();
        if (!valid) {
            this._blockWithMissingFieldsNotice(missing, missingNames);
            return;
        }
        // Already validated above - the interceptor below would just
        // repeat the same (now-passing) check, so skip it.
        this._clickTab(this.nextLabel, { skipValidation: true });
    }

    // --- Tab-header click interception -------------------------------
    // Without this, a user can bypass the Next button entirely by
    // clicking directly on any tab header in the top nav bar, which
    // defeats the whole point of gating required fields per step.
    _bindTabInterceptor() {
        const navTabs = this._getNavTabs();
        if (!navTabs) {
            return;
        }
        // Several ProfileStepNav instances share the same .nav-tabs bar
        // (one per page); only bind once per bar, not once per instance.
        if (navTabs.dataset.profileStepNavBound === "1") {
            return;
        }
        navTabs.dataset.profileStepNavBound = "1";
        navTabs.addEventListener("click", this._onNavTabsClickCapture, true);
        this._boundNavTabs = navTabs;
    }

    _unbindTabInterceptor() {
        if (this._boundNavTabs) {
            this._boundNavTabs.removeEventListener(
                "click",
                this._onNavTabsClickCapture,
                true
            );
            delete this._boundNavTabs.dataset.profileStepNavBound;
            this._boundNavTabs = null;
        }
    }

    _onNavTabsClickCapture(ev) {
        // Only the instance whose own page is currently visible should
        // act - all the others bail out immediately, so a given click is
        // only ever handled once even though up to 8 instances share the
        // same bound listener element.
        if (!this._isOwnPaneActive()) {
            return;
        }
        const navTabs = this._getNavTabs();
        const link = ev.target.closest(".nav-link");
        if (!link || !navTabs || !navTabs.contains(link)) {
            return;
        }
        // Clicking the already-active tab's own header - nothing to
        // validate, let it through untouched.
        if (link.textContent.trim() === (this._getOwnLabel() || "")) {
            return;
        }
        // Our own onPrev()/onNext() mark their synthetic clicks so we
        // don't re-validate (or wrongly block Previous) here.
        if (link.dataset.profileStepSkipValidation === "1") {
            delete link.dataset.profileStepSkipValidation;
            return;
        }
        const { valid, missing, missingNames } = this._validateRequired();
        if (!valid) {
            ev.preventDefault();
            ev.stopPropagation();
            ev.stopImmediatePropagation();
            this._blockWithMissingFieldsNotice(missing, missingNames);
        }
    }

    _getOwnLabel() {
        const pane = this._getOwnPane();
        if (!pane) {
            return null;
        }
        const navTabs = this._getNavTabs();
        if (!navTabs) {
            return null;
        }
        // The pane's own nav-link is the one whose aria-controls /
        // data-bs-target references this pane's id, if present; falling
        // back to matching by DOM order keeps this working even without
        // those attributes.
        const paneId = pane.id;
        if (paneId) {
            const byId = navTabs.querySelector(
                `[data-bs-target="#${CSS.escape(paneId)}"], [aria-controls="${CSS.escape(paneId)}"]`
            );
            if (byId) {
                return byId.textContent.trim();
            }
        }
        const panes = Array.from(pane.parentElement ? pane.parentElement.children : []);
        const links = navTabs.querySelectorAll(".nav-link");
        const idx = panes.indexOf(pane);
        if (idx >= 0 && links[idx]) {
            return links[idx].textContent.trim();
        }
        return null;
    }
}

registry.category("view_widgets").add("profile_step_nav", {
    component: ProfileStepNav,
    extractProps: ({ attrs }) => ({
        options: attrs.options ? evaluateExpr(attrs.options) : {},
    }),
});
