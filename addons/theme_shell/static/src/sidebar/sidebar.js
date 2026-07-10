/** @odoo-module **/

import { Component, useState, onWillStart, useRef, useExternalListener } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

const THEME_STORAGE_KEY = "o_theme_sidebar_theme";

/**
 * The actual flyout content, rendered via usePopover — meaning it is
 * portalled to the document root, NOT nested inside the sidebar's
 * overflow:auto container. This is what fixes the clipping/squeezing:
 * a portalled element isn't a descendant of the scrolling ancestor, so
 * it can't be clipped by it, and it gets Odoo's popover z-index layer
 * (already above normal page content) instead of whatever stacking
 * context the sidebar happens to sit in.
 *
 * VERIFY: import path "@web/core/popover/popover_hook" is my best-
 * confidence recollection of Odoo's core popover hook location and API
 * shape (open(target, props) / close() / isOpen). If this throws on
 * your version, send me the console error and I'll adjust.
 */
export class SidebarFlyoutPanel extends Component {
    static template = "theme_shell.SidebarFlyoutPanel";
    static props = {
        items: Array,
        onLeafClick: Function,
        close: { type: Function, optional: true }, // injected by usePopover itself
    };
}

/**
 * Recursive menu row. Click-to-open/close (not hover-driven) — this was
 * changed from an earlier hover+timer version because hover-based nested
 * flyouts were hard for non-technical users to control precisely. Since
 * every popover already has closeOnClickAway: true, clicking a leaf item
 * anywhere in a nested chain closes the whole chain naturally, because
 * each level is portalled separately and a click on a leaf counts as
 * "outside" every ancestor popover's own DOM.
 */
export class SidebarMenuItem extends Component {
    static template = "theme_shell.SidebarMenuItem";
    static props = {
        item: Object,
        onLeafClick: Function,
    };
    static components = { SidebarFlyoutPanel };

    setup() {
        this.rootRef = useRef("root");
        this.popover = usePopover(SidebarFlyoutPanel, {
            position: "right-start",
            closeOnClickAway: true,
        });
    }

    get hasChildren() {
        return !!(this.props.item.childrenTree && this.props.item.childrenTree.length);
    }

    onClick() {
        if (!this.hasChildren) {
            this.props.onLeafClick(this.props.item);
            return;
        }
        // VERIFY: `this.popover.isOpen` is my best-confidence recollection of
        // usePopover's exposed state for "is this popover currently shown".
        // If clicking twice doesn't toggle closed, check the console for an
        // error here — the property name may differ slightly on your version.
        if (this.popover.isOpen) {
            this.popover.close();
            return;
        }
        this.popover.open(this.rootRef.el, {
            items: this.props.item.childrenTree,
            // Wrapped rather than passed straight through: whichever leaf
            // eventually gets clicked, no matter how deep, first closes
            // *this* level's popover, then calls the onLeafClick it was
            // given — which is itself another one of these wrapped closures
            // for every level above it. That's what makes the whole chain
            // collapse in one click instead of just navigating and leaving
            // every ancestor panel hanging open.
            onLeafClick: (menuItem) => {
                this.popover.close();
                this.props.onLeafClick(menuItem);
            },
        });
    }
}
SidebarFlyoutPanel.components = { SidebarMenuItem };

/**
 * Persistent sidebar that replaces the top NavBar app-switcher (9-dot grid)
 * and the horizontal top menu. Everything lives in one always-visible column.
 *
 * NOTE: this reuses Odoo's own "menu", "user" and "company" services, the
 * same sources of truth the stock NavBar already uses. We are not
 * reinventing menu/user/company data, only how it's displayed.
 *
 * VERIFY AGAINST YOUR OWN SOURCE before relying on this in production:
 *   - web/static/src/webclient/menus/menu_service.js
 *       -> getApps / getCurrentApp / getMenuAsTree / selectMenu
 *   - web/static/src/webclient/user_menu / user_service
 *       -> exact property names for user's display name and id
 *   - web/static/src/webclient/company_service.js (or similar)
 *       -> exact property name for the active company on currentCompany
 */
export class Sidebar extends Component {
    static template = "theme_shell.Sidebar";
    static components = { SidebarMenuItem };
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.userService = user;

        this.companyService = null;
        try {
            this.companyService = useService("company");
        } catch (e) {
            console.warn("theme_shell: 'company' service unavailable", e);
        }

        // Read saved theme preference. Wrapped in try/catch since
        // localStorage can throw in some contexts (e.g. private
        // browsing on Safari, or if third-party storage is blocked).
        let savedTheme = "light";
        try {
            savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || "light";
        } catch (e) {
            console.warn("theme_shell: localStorage unavailable, defaulting to light theme", e);
        }

        this.state = useState({
            collapsed: false,
            apps: [],
            currentAppId: null,      // which app's page is actually open
            expandedAppId: null,     // which app's submenu list is expanded
            currentAppSubmenus: [],
            profileOpen: false,
            theme: savedTheme,       // 'light' (default) or 'dark'
            searchQuery: "",
            highlightedIndex: -1,    // for arrow-key navigation through results
            // Flat list built once at startup so search covers every app
            // AND every nested menu item, not just what's currently
            // expanded/visible. See buildSearchIndex() below.
            searchIndex: [],
        });

        // Apply the saved theme to <body> immediately so the very first
        // paint is already correct, not a flash of the default theme.
        if (savedTheme === "dark") {
            document.body.classList.add("o_theme_sidebar_dark");
        }

        this.profileRef = useRef("profileContainer");
        this.searchInputRef = useRef("searchInput");

        useExternalListener(document, "click", (ev) => {
            if (this.state.profileOpen && this.profileRef.el && !this.profileRef.el.contains(ev.target)) {
                this.state.profileOpen = false;
            }
        });

        onWillStart(async () => {
            try {
                this.state.apps = this.menuService.getApps();
                const current = this.menuService.getCurrentApp();
                if (current) {
                    this.state.currentAppId = current.id;
                    this.state.expandedAppId = current.id;
                    this.state.currentAppSubmenus = this.menuService.getMenuAsTree(current.id).childrenTree || [];
                }
                this.buildSearchIndex();
            } catch (e) {
                console.error("theme_shell: failed to load menu data", e);
            }
        });
    }

    // Walks every app's full menu tree once at startup and flattens it
    // into a single searchable list — top-level apps themselves, plus
    // every leaf menu item, each carrying a breadcrumb-style "path" for
    // display (e.g. "Accounting › Configuration › Chart of Accounts").
    // NOTE: on installs with a very large number of apps/menu items this
    // does more upfront work than the previous "only load the current
    // app's tree" approach — if it feels sluggish on your data size,
    // flag it and this can be made lazy/on-demand instead.
    buildSearchIndex() {
        const index = [];
        for (const app of this.state.apps) {
            index.push({
                id: `app-${app.id}`,
                name: app.name,
                path: app.name,
                isApp: true,
                appObj: app,
            });
            try {
                const tree = this.menuService.getMenuAsTree(app.id);
                this.flattenMenuIntoIndex(tree.childrenTree || [], app, app.name, index);
            } catch (e) {
                // Some apps may not expose a menu tree — skip, don't
                // block the rest of the index from building.
                console.warn(`theme_shell: could not index menu for app "${app.name}"`, e);
            }
        }
        this.state.searchIndex = index;
    }

    flattenMenuIntoIndex(items, app, pathPrefix, index) {
        for (const item of items) {
            const path = `${pathPrefix} › ${item.name}`;
            if (item.childrenTree && item.childrenTree.length) {
                this.flattenMenuIntoIndex(item.childrenTree, app, path, index);
            } else {
                index.push({
                    id: `item-${item.id}`,
                    name: item.name,
                    path,
                    isApp: false,
                    appId: app.id,
                    menuItem: item,
                });
            }
        }
    }

    // Deliberately not exact-match: a substring hit ("date" matching
    // "Date Ranges") ranks above a fuzzy hit, but a fuzzy subsequence
    // match ("drt" matching "Date Ranges") still counts, same idea as a
    // command-palette fuzzy finder rather than a strict search box.
    fuzzySubsequenceMatch(text, query) {
        let ti = 0;
        for (const ch of query) {
            ti = text.indexOf(ch, ti);
            if (ti === -1) {
                return false;
            }
            ti++;
        }
        return true;
    }

    get searchResults() {
        const q = this.state.searchQuery.trim().toLowerCase();
        if (!q) {
            return [];
        }
        const substringMatches = [];
        const fuzzyMatches = [];
        for (const entry of this.state.searchIndex) {
            const nameLower = entry.name.toLowerCase();
            if (nameLower.includes(q)) {
                substringMatches.push(entry);
            } else if (this.fuzzySubsequenceMatch(nameLower, q)) {
                fuzzyMatches.push(entry);
            }
        }
        // Cap results so a broad/short query (e.g. a single letter)
        // doesn't dump the entire menu tree into the sidebar at once.
        return [...substringMatches, ...fuzzyMatches].slice(0, 30);
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
        this.state.highlightedIndex = -1;
    }

    onSearchKeydown(ev) {
        const results = this.searchResults;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            if (results.length) {
                this.state.highlightedIndex = (this.state.highlightedIndex + 1) % results.length;
            }
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            if (results.length) {
                this.state.highlightedIndex = (this.state.highlightedIndex - 1 + results.length) % results.length;
            }
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            const target = results[this.state.highlightedIndex] || (results.length === 1 ? results[0] : null);
            if (target) {
                this.onSearchResultClick(target);
            }
        } else if (ev.key === "Escape") {
            this.state.searchQuery = "";
            this.state.highlightedIndex = -1;
            this.searchInputRef.el?.blur();
        }
    }

    onSearchResultClick(result) {
        this.state.searchQuery = "";
        this.state.highlightedIndex = -1;
        this.state.profileOpen = false;
        if (result.isApp) {
            this.onClickApp(result.appObj);
            return;
        }
        this.state.expandedAppId = result.appId;
        this.state.currentAppId = result.appId;
        this.state.currentAppSubmenus = this.menuService.getMenuAsTree(result.appId).childrenTree || [];
        this.menuService.selectMenu(result.menuItem);
    }

    get companyName() {
        return this.companyService?.currentCompany?.name || "";
    }

    get userName() {
        return this.userService?.name || "";
    }

    get userAvatarUrl() {
        const uid = this.userService?.userId;
        return uid ? `/web/image?model=res.users&id=${uid}&field=avatar_128` : "";
    }

    toggleCollapsed() {
        this.state.collapsed = !this.state.collapsed;
        // Mirror onto <body> so the CSS layout override (separate file,
        // can't see component state) can react without relying on :has().
        document.body.classList.toggle("o_theme_sidebar_is_collapsed", this.state.collapsed);
    }

    toggleTheme() {
        this.state.theme = this.state.theme === "light" ? "dark" : "light";
        document.body.classList.toggle("o_theme_sidebar_dark", this.state.theme === "dark");
        try {
            localStorage.setItem(THEME_STORAGE_KEY, this.state.theme);
        } catch (e) {
            console.warn("theme_shell: failed to persist theme preference", e);
        }
    }

    toggleProfileMenu() {
        this.state.profileOpen = !this.state.profileOpen;
    }

    logout() {
        window.location.href = "/web/session/logout";
    }

    onClickApp(app) {
        this.state.profileOpen = false; // close profile menu whenever another app is opened

        if (this.state.expandedAppId === app.id) {
            // Clicking the already-expanded app again just collapses its
            // submenu list. The currently open page is left untouched —
            // this is the "click again to collapse" behavior you asked for.
            this.state.expandedAppId = null;
            return;
        }

        this.state.expandedAppId = app.id;
        this.state.currentAppId = app.id;
        this.state.currentAppSubmenus = this.menuService.getMenuAsTree(app.id).childrenTree || [];
        this.menuService.selectMenu(app);
    }

    // Arrow field (not a prototype method) so `this` stays bound correctly
    // when this function is handed down as a prop through several levels
    // of recursive SidebarMenuItem components.
    onLeafClick = (menuItem) => {
        this.menuService.selectMenu(menuItem);
    };
}

registry.category("main_components").add("Sidebar", {
    Component: Sidebar,
});
