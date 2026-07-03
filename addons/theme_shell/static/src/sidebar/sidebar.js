/** @odoo-module **/

import {
  Component,
  useState,
  onWillStart,
  useRef,
  useExternalListener,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

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
 * shape (open(target, props) / close()). Given the useService("user")
 * surprise last round, I'd rather flag this again than assume — if this
 * throws on your version, send me the console error the same way and
 * I'll adjust the import path or fall back to a manual implementation.
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
 * Recursive menu row.
 * - No children -> leaf, click navigates (selectMenu).
 * - Has children -> hovering opens a portalled SidebarFlyoutPanel next to
 *   this row (via usePopover), instead of rendering inline children that
 *   would get clipped by the sidebar's own scroll container.
 *
 * Every nesting level is just another instance of this same component,
 * so the "escape the clipping container" fix applies uniformly no matter
 * how deep the menu goes — there's no special-casing per level.
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
    return !!(
      this.props.item.childrenTree && this.props.item.childrenTree.length
    );
  }

  onClick() {
    if (!this.hasChildren) {
      this.props.onLeafClick(this.props.item);
      return;
    }
    // VERIFY: `this.popover.isOpen` is my best-confidence recollection of
    // usePopover's exposed state for "is this popover currently shown".
    // If clicking twice doesn't toggle closed, check your console for an
    // error here — the property name may differ slightly on your version.
    if (this.popover.isOpen) {
      this.popover.close();
      return;
    }
    this.popover.open(this.rootRef.el, {
      items: this.props.item.childrenTree,
      onLeafClick: this.props.onLeafClick,
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
 * These are stable in shape across 16-18 in my knowledge, but I don't have
 * your literal files open, so treat the property names below as "very
 * likely correct, confirm in 30 seconds" rather than guaranteed.
 */
export class Sidebar extends Component {
  static template = "theme_shell.Sidebar";
  static components = { SidebarMenuItem };
  static props = {};

  setup() {
    this.menuService = useService("menu");
    this.actionService = useService("action");

    // Confirmed via your console error: 'user' is NOT a registered
    // Odoo service on your version — it's a plain importable object
    // instead (see the `user` import above). Fixed to match reality.
    this.userService = user;

    this.companyService = null;
    try {
      this.companyService = useService("company");
    } catch (e) {
      console.warn("theme_shell: 'company' service unavailable", e);
    }

    this.state = useState({
      collapsed: false,
      apps: [],
      currentAppId: null, // which app's page is actually open
      expandedAppId: null, // which app's submenu list is expanded
      currentAppSubmenus: [],
      profileOpen: false,
    });
    this.profileRef = useRef("profileContainer");

    useExternalListener(document, "click", (ev) => {
      if (
        this.state.profileOpen &&
        this.profileRef.el &&
        !this.profileRef.el.contains(ev.target)
      ) {
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
          this.state.currentAppSubmenus =
            this.menuService.getMenuAsTree(current.id).childrenTree || [];
        }
      } catch (e) {
        console.error("theme_shell: failed to load menu data", e);
      }
    });
  }

  get companyName() {
    // Verify "currentCompany.name" against your company_service.js.
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
    document.body.classList.toggle(
      "o_theme_sidebar_is_collapsed",
      this.state.collapsed,
    );
  }

  toggleProfileMenu() {
    this.state.profileOpen = !this.state.profileOpen;
  }

  logout() {
    // Standard Odoo logout route.
    window.location.href = "/web/session/logout";
  }

  onClickApp(app) {
    this.state.profileOpen = false;
    if (this.state.expandedAppId === app.id) {
      // Clicking the already-expanded app again just collapses its
      // submenu list. The currently open page is left untouched —
      // this is the "click again to collapse" behavior you asked for.
      this.state.expandedAppId = null;
      return;
    }

    this.state.expandedAppId = app.id;
    this.state.currentAppId = app.id;
    this.state.currentAppSubmenus =
      this.menuService.getMenuAsTree(app.id).childrenTree || [];
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
