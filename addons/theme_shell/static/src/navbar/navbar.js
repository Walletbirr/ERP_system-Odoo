/** @odoo-module **/

import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

/**
 * Portalled dropdown content (via usePopover) — same mechanism as before,
 * just reused here for both app dropdowns (open downward) and nested
 * flyouts (open sideways).
 */
export class NavFlyoutPanel extends Component {
    static template = "theme_shell.NavFlyoutPanel";
    static props = {
        items: Array,
        onLeafClick: Function,
        close: { type: Function, optional: true },
    };
}

/**
 * A single row inside a dropdown/flyout (i.e. NOT a top-level app in the
 * horizontal bar — see NavAppItem for that). Same click-to-toggle logic
 * as the previous sidebar version: leaf -> navigate, has children -> open
 * a further flyout to the right, since we're now nested inside a panel
 * rather than sitting in a scrollable column.
 */
export class NavMenuItem extends Component {
    static template = "theme_shell.NavMenuItem";
    static props = {
        item: Object,
        onLeafClick: Function,
    };
    static components = { NavFlyoutPanel };

    setup() {
        this.rootRef = useRef("root");
        this.state = useState({ open: false });
        this.popover = usePopover(NavFlyoutPanel, {
            position: "right-start",
            closeOnClickAway: true,
            onClose: () => {
                this.state.open = false;
            },
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
        if (this.state.open) {
            this.popover.close();
            this.state.open = false;
        } else if (this.rootRef.el) {
            this.popover.open(this.rootRef.el, {
                items: this.props.item.childrenTree,
                onLeafClick: this.props.onLeafClick,
            });
            this.state.open = true;
        }
    }
}
NavFlyoutPanel.components = { NavMenuItem };

/**
 * A top-level app in the horizontal bar (e.g. "Sales", "Accounting").
 * Distinct from NavMenuItem because:
 *  - it renders an icon + label chip, not a plain text row
 *  - its dropdown opens BELOW it ("bottom-start"), not beside it
 *  - it tracks "is this the currently open app" for active styling,
 *    which nested items don't need
 *  - clicking an app with no submenu at all just navigates directly,
 *    rather than opening an empty dropdown
 */
export class NavAppItem extends Component {
    static template = "theme_shell.NavAppItem";
    static props = {
        app: Object,
        isActive: Boolean,
        menuService: Object,
        onAppClick: Function,
    };
    static components = { NavFlyoutPanel };

    setup() {
        this.rootRef = useRef("root");
        this.state = useState({ open: false });
        this.popover = usePopover(NavFlyoutPanel, {
            position: "bottom-start",
            closeOnClickAway: true,
            onClose: () => {
                this.state.open = false;
            },
        });
    }

    get children() {
        return this.props.menuService.getMenuAsTree(this.props.app.id).childrenTree || [];
    }

    onClick() {
        const children = this.children;
        // Always navigate to the app itself on click, same as a normal
        // navbar app click would.
        this.props.onAppClick(this.props.app);

        if (!children.length) {
            return;
        }
        if (this.state.open) {
            this.popover.close();
            this.state.open = false;
        } else if (this.rootRef.el) {
            this.popover.open(this.rootRef.el, {
                items: children,
                onLeafClick: (item) => this.props.onAppClick(item, false),
            });
            this.state.open = true;
        }
    }
}

/**
 * The horizontal top bar itself: brand on the left, every app listed
 * inline (no 9-dot grid, no hidden menu), profile/logout on the right.
 *
 * VERIFY (same caveats as the sidebar version, unchanged by this rewrite):
 *  - menuService method names (getApps / getCurrentApp / getMenuAsTree / selectMenu)
 *  - companyService.currentCompany.name
 *  - usePopover's exact API shape (open/close/onClose)
 * `user` import already confirmed working against your console error earlier.
 */
export class TopNavbar extends Component {
    static template = "theme_shell.TopNavbar";
    static components = { NavAppItem };
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.userService = user;

        this.companyService = null;
        try {
            this.companyService = useService("company");
        } catch (e) {
            console.warn("theme_shell: 'company' service unavailable", e);
        }

        this.state = useState({
            apps: [],
            currentAppId: null,
            profileOpen: false,
        });

        onWillStart(async () => {
            try {
                this.state.apps = this.menuService.getApps();
                const current = this.menuService.getCurrentApp();
                if (current) {
                    this.state.currentAppId = current.id;
                }
            } catch (e) {
                console.error("theme_shell: failed to load menu data", e);
            }
        });
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

    toggleProfileMenu() {
        this.state.profileOpen = !this.state.profileOpen;
    }

    logout() {
        window.location.href = "/web/session/logout";
    }

    onAppClick = (item, isTopLevelApp = true) => {
        if (isTopLevelApp) {
            this.state.currentAppId = item.id;
        }
        this.menuService.selectMenu(item);
    };
}

registry.category("main_components").add("TopNavbar", {
    Component: TopNavbar,
});
