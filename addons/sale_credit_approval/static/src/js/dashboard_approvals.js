/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useExternalListener } from "@odoo/owl";
import { BhManagementDashboard } from "@bh_management_dashboard/js/dashboard";

// Adds several things to the Executive Dashboard component. The markup for
// all of it lives in static/src/xml/dashboard_approvals.xml (a normal
// xpath template extension) - this file only supplies the methods that
// markup calls:
//
// 1. The "Approvals" tab (setTabApprovals - reuses the base component's
//    already-generic _setTab, nothing else needed), including a search box,
//    status filter, and a 10-per-page paginated "Recent Credit Approval
//    Requests" table.
// 2. The "Requests Needing Your Action" panel on the Sales tab: a
//    5-per-page paginated table of orders the CURRENT user can act on,
//    where clicking a row opens that Sales Order. Approving/rejecting
//    itself happens on the order's own form (its header already has the
//    Approve/Reject buttons from this module's other views) or from the
//    full Credit Approvals list - this dashboard is for finding the
//    request quickly, not a duplicate action surface.
// 3. A notification bell in the top navbar (replaces the static company
//    name/tagline text there) showing the same "needs your action" count
//    as a badge, with a dropdown preview. Since this reads from the same
//    state.data.approvals.action_required the Sales-tab panel uses, it
//    naturally goes to 0 / empties out the next time the dashboard
//    component reloads its data (mount, refresh, or period change) after
//    the manager approves/rejects - no separate read/unread tracking is
//    needed because "needing your action" already means "not yet decided".
const ACTIONS_PAGE_SIZE = 5;
const RECENT_PAGE_SIZE = 10;
const NOTIF_PREVIEW_LIMIT = 5;

patch(BhManagementDashboard.prototype, {
    setup() {
        super.setup();
        this.action = useService("action");
        this.state.actionsPage = 0;
        this.state.recentPage = 0;
        this.state.recentSearch = "";
        this.state.recentStatusFilter = "all";
        this.state.notifOpen = false;

        // Close the notification dropdown on any click outside it. The
        // handler only acts while it's open, and checks the click target
        // against the bell/dropdown container - a click on the bell itself
        // is inside that container, so it won't immediately re-close what
        // onToggleNotifDropdown just opened.
        useExternalListener(window, "click", (ev) => {
            if (!this.state.notifOpen) return;
            const root = ev.target.closest && ev.target.closest(".bh-topnav-notif");
            if (!root) this.state.notifOpen = false;
        });
    },

    async loadData() {
        await super.loadData();
        // A fresh fetch can shrink or reorder the "needs your action"
        // list (e.g. someone else just approved one) - start back on
        // page 1 rather than possibly landing on a now-empty page.
        // Same idea for the Recent table - keep the search text/status
        // filter (the user is likely still looking for the same thing)
        // but reset the page.
        this.state.actionsPage = 0;
        this.state.recentPage = 0;
    },

    setTabApprovals() {
        this._setTab("approvals");
    },

    _actionRequiredList() {
        return (this.state.data && this.state.data.approvals && this.state.data.approvals.action_required) || [];
    },

    actionsPageCount() {
        return Math.max(1, Math.ceil(this._actionRequiredList().length / ACTIONS_PAGE_SIZE));
    },

    actionsPage() {
        const start = this.state.actionsPage * ACTIONS_PAGE_SIZE;
        return this._actionRequiredList().slice(start, start + ACTIONS_PAGE_SIZE);
    },

    onActionsPrev() {
        if (this.state.actionsPage > 0) this.state.actionsPage--;
    },

    onActionsNext() {
        if (this.state.actionsPage + 1 < this.actionsPageCount()) this.state.actionsPage++;
    },

    onOpenOrder(orderId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "sale.order",
            res_id: orderId,
            views: [[false, "form"]],
            target: "current",
        });
    },

    // ── "Recent Credit Approval Requests" table (Approvals tab) ────────────
    // Search + status filter + pagination over the (backend-capped-at-200)
    // `recent` list. Filtering client-side is fine here since the list is
    // small and this avoids an extra round-trip on every keystroke.

    _recentAllList() {
        return (this.state.data && this.state.data.approvals && this.state.data.approvals.recent) || [];
    },

    _recentList() {
        const all = this._recentAllList();
        const status = this.state.recentStatusFilter || "all";
        const q = (this.state.recentSearch || "").trim().toLowerCase();
        return all.filter((o) => {
            if (status !== "all" && o.state !== status) return false;
            if (!q) return true;
            return (
                (o.name || "").toLowerCase().includes(q) ||
                (o.customer || "").toLowerCase().includes(q) ||
                (o.salesperson || "").toLowerCase().includes(q) ||
                (o.payment_term || "").toLowerCase().includes(q)
            );
        });
    },

    recentPageCount() {
        return Math.max(1, Math.ceil(this._recentList().length / RECENT_PAGE_SIZE));
    },

    recentPageItems() {
        const start = this.state.recentPage * RECENT_PAGE_SIZE;
        return this._recentList().slice(start, start + RECENT_PAGE_SIZE);
    },

    onRecentSearchInput(ev) {
        this.state.recentSearch = ev.target.value;
        this.state.recentPage = 0; // new search - back to page 1
    },

    onRecentStatusFilterChange(ev) {
        this.state.recentStatusFilter = ev.target.value;
        this.state.recentPage = 0; // new filter - back to page 1
    },

    onRecentPrev() {
        if (this.state.recentPage > 0) this.state.recentPage--;
    },

    onRecentNext() {
        if (this.state.recentPage + 1 < this.recentPageCount()) this.state.recentPage++;
    },

    // ── Notification bell (top navbar) ──────────────────────────────────
    // Same underlying list as the Sales-tab "Requests Needing Your Action"
    // panel - just a compact preview + count badge that's visible no
    // matter which tab the manager is on.

    onToggleNotifDropdown() {
        this.state.notifOpen = !this.state.notifOpen;
    },

    notifPreviewList() {
        return this._actionRequiredList().slice(0, NOTIF_PREVIEW_LIMIT);
    },

    notifOverflowCount() {
        return Math.max(0, this._actionRequiredList().length - NOTIF_PREVIEW_LIMIT);
    },

    onNotifItemClick(orderId) {
        this.state.notifOpen = false;
        this.onOpenOrder(orderId);
    },

    onViewAllNotifs() {
        this.state.notifOpen = false;
        this.state.recentStatusFilter = "to_approve"; // pre-filter to Pending
        this.state.recentPage = 0;
        this.setTabApprovals();
    },
});
