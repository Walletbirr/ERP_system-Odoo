/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";

/**
 * Two independent motion effects, since "page to page" and "tab to
 * tab" have two completely different triggers under the hood:
 *
 * 1. PAGE-TO-PAGE: a centered 12-dot "fading circle" spinner overlay
 *    + a fade-in on the action container once the new page lands.
 *    - START signal: sidebar.js fires "theme_shell:nav-start" on the
 *      bus itself, right where it already calls into the menu/action
 *      services (onClickApp / onLeafClick / onSearchResultClick).
 *      Deliberately NOT done by patching Odoo's core action service —
 *      an earlier version of this did that, and a mismatched import
 *      broke the entire backend bundle (blank white screen). Firing
 *      the signal from code we already own can never break real
 *      navigation, only the cosmetic overlay/fade sitting on top.
 *    - FINISH signal: a MutationObserver on `.o_action_manager`
 *      watching for its children being replaced — pure DOM
 *      observation, no core internals involved. A short fallback
 *      timeout also force-finishes in case a click doesn't end up
 *      swapping the DOM at all (e.g. re-clicking the already open
 *      page), so the spinner can never get stuck on screen.
 *
 * 2. TAB-TO-TAB: Odoo's Notebook component (tabs inside a form, e.g.
 *    "Other Info" / "Invoicing") never goes through app navigation at
 *    all — it's a pure client-side state flip, no RPC — so it needs
 *    its own trigger: a delegated click listener on the tab headers.
 *
 * VERIFY: ".o_notebook_headers .nav-link" is my best-confidence guess
 * for Odoo 18's notebook tab-header markup. If clicking a tab doesn't
 * fade the panel below it, inspect that tab header in devtools and
 * send me the real class name. This one is safely inert if wrong —
 * worst case is simply "no tab fade", never a broken page, since it's
 * just an event-delegation listener, not an import/patch.
 */
export class PageTransitions extends Component {
    static template = "theme_shell.PageTransitions";
    static props = {};

    setup() {
        this.overlayRef = useRef("overlay");
        this.hideTimer = null;
        this.finishFallbackTimer = null;
        this.actionObserver = null;

        // The DOM swap on a fast local navigation can happen in well
        // under 100ms — too quick to actually perceive. Enforcing a
        // floor here means the spinner is always on screen long enough
        // to register, even when the real load is basically instant.
        this.MIN_VISIBLE_MS = 550;
        this.loadStartedAt = 0;
        this.isLoading = false;

        useBus(this.env.bus, "theme_shell:nav-start", () => this.startLoading());

        this.onDocumentClick = this.onDocumentClick.bind(this);
        onMounted(() => {
            document.addEventListener("click", this.onDocumentClick, true);
            const target = document.querySelector(".o_action_manager");
            if (target) {
                this.actionObserver = new MutationObserver((mutations) => {
                    if (mutations.some((m) => m.addedNodes.length > 0)) {
                        this.finishLoading();
                    }
                });
                this.actionObserver.observe(target, { childList: true });
            }
        });
        onWillUnmount(() => {
            document.removeEventListener("click", this.onDocumentClick, true);
            this.actionObserver?.disconnect();
            clearTimeout(this.hideTimer);
            clearTimeout(this.finishFallbackTimer);
        });
    }

    startLoading() {
        const overlay = this.overlayRef.el;
        if (!overlay) {
            return;
        }
        clearTimeout(this.hideTimer);
        clearTimeout(this.finishFallbackTimer);
        this.isLoading = true;
        this.loadStartedAt = performance.now();
        overlay.classList.remove("o_theme_loader_hidden");

        // Safety net: if no DOM swap is observed within 4s (e.g. the
        // click didn't actually change the page), finish anyway so the
        // spinner never sits stuck on screen.
        this.finishFallbackTimer = setTimeout(() => this.finishLoading(), 4000);
    }

    finishLoading() {
        if (!this.isLoading) {
            // Already finished (or never started) — happens when the
            // MutationObserver fires more than once for a single page
            // load (e.g. several child nodes added in separate batches).
            return;
        }
        clearTimeout(this.finishFallbackTimer);

        const hideNow = () => {
            this.isLoading = false;
            const overlay = this.overlayRef.el;
            if (overlay) {
                overlay.classList.add("o_theme_loader_hidden");
            }
            // Force the page-fade to replay even if Odoo reused the DOM
            // node instead of remounting it fresh.
            const target = document.querySelector(".o_action_manager");
            if (target) {
                target.classList.remove("o_theme_page_fade");
                void target.offsetWidth;
                target.classList.add("o_theme_page_fade");
            }
        };

        const elapsed = performance.now() - this.loadStartedAt;
        const remaining = this.MIN_VISIBLE_MS - elapsed;
        if (remaining > 0) {
            this.hideTimer = setTimeout(hideNow, remaining);
        } else {
            hideNow();
        }
    }

    onDocumentClick(ev) {
        const tabLink = ev.target.closest(".o_notebook_headers .nav-link");
        if (!tabLink) {
            return;
        }
        const notebook = tabLink.closest(".o_notebook");
        // Wait one frame: Odoo hasn't flipped which pane carries the
        // "active" class yet at the exact moment this click fires.
        requestAnimationFrame(() => {
            const pane =
                notebook?.querySelector(".o_notebook_content .tab-pane.active") ||
                notebook?.querySelector(".o_notebook_content > *");
            if (pane) {
                pane.classList.remove("o_theme_tab_fade");
                void pane.offsetWidth;
                pane.classList.add("o_theme_tab_fade");
            }
        });
    }
}

registry.category("main_components").add("PageTransitions", {
    Component: PageTransitions,
});
