/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onWillUnmount, useEffect, useExternalListener } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/**
 * VERIFY: relies on the global `Chart` constructor from
 * web/static/lib/Chart/Chart.js, declared in this module's manifest.
 */
export class BingetDashboard extends Component {
    static template = "binget_dashboard.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.trendChartRef = useRef("trendChart");
        this.purchaseTrendChartRef = useRef("purchaseTrendChart");
        this.agingChartRef = useRef("agingChart");
        this.employeeGrowthChartRef = useRef("employeeGrowthChart");
        this.departmentPieChartRef = useRef("departmentPieChart");
        this.revenueOverviewChartRef = useRef("revenueOverviewChart");
        this.revenueOverviewCardRef = useRef("revenueOverviewCard");
        this.dateSelectorRef = useRef("dateSelector");
        this.explorerCardRef = useRef("explorerCard");
        this.trendChartInstance = null;
        this.purchaseTrendChartInstance = null;
        this.agingChartInstance = null;
        this.employeeGrowthChartInstance = null;
        this.departmentPieChartInstance = null;
        this.revenueOverviewChartInstance = null;
        this._productLookupTimer = null;

        const today = new Date();
        this.monthLabels = MONTH_LABELS;

        this.state = useState({
            view: "main", // 'main' | 'branch'
            activeTab: "overview",
            // Unified date scope: 'month' shows one calendar month,
            // 'year' shows the whole year, 'custom' is an explicit
            // From/To range. All three clamp to today so you never
            // silently query into the future.
            dateScope: "month",
            selectedMonth: today.getMonth() + 1,
            selectedYear: today.getFullYear(),
            customFrom: new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6).toISOString().slice(0, 10),
            customTo: today.toISOString().slice(0, 10),
            dateFrom: "",
            dateTo: "",
            dateSelectorOpen: false,
            // Draft values live only while the popover is open; nothing
            // here affects the dashboard until explicitly committed.
            dateDraft: {
                scope: "month", month: today.getMonth() + 1, year: today.getFullYear(),
                customFrom: "", customTo: "",
            },
            companyId: "",
            trendChartType: "line",
            loading: true,
            showConfig: false,
            config: {},
            roleProfile: { is_admin: false, roles: [], display_name: "Business Dashboard", tabs: [{ key: "overview", label: "Overview", icon: "fa-th-large" }], visible_kpis: [], user_name: "" },
            filterOptions: { locations: [], warehouses: [], companies: [] },
            data: {
                kpis: {}, sales_trend: { rows: [] }, top_customers: { rows: [] }, top_products: { rows: [] },
                pipeline: { stages: [] },
                purchase_trend: { rows: [] }, top_vendors: { rows: [] }, top_purchased_products: { rows: [] },
                purchase_pipeline: { stages: [] },
                inventory_summary: {}, cash_flow: { ar_aging: [] }, top_overdue_customers: { rows: [] },
                procurement: {}, workforce: {}, manufacturing: {}, activity: { rows: [] },
                revenue_overview: { labels: [], revenue: [], expenses: [], total_revenue: 0, total_expenses: 0, net_amount: 0, net_margin_pct: 0 },
            },
            branches: { rows: [] },
            branchDetail: {
                loading: false, data: null, showInventory: false,
                // Independent from the Inventory tab's Explorer state so
                // browsing a branch's stock never disturbs whatever
                // filters were set on the main Inventory tab.
                explorer: { locationId: "", status: "all", rows: [], total: 0, offset: 0, limit: 20, loading: false },
            },
            productLookup: { query: "", rows: [], loading: false },
            // Inventory Explorer has its own filters/loading, separate
            // from the main overview call, since it's a potentially
            // large, independently-paginated dataset.
            explorer: {
                warehouseId: "", locationId: "", status: "all",
                rows: [], total: 0, offset: 0, limit: 20, loading: false, expanded: false,
            },
            activityLog: {
                rows: [], total: 0, offset: 0, limit: 20, loading: false,
                typeFilter: "all", userId: "", search: "",
                users: [], loaded: false,
                // Set on a failed RPC only, cleared on the next attempt
                // (success or fail). Kept separate from an empty `rows`
                // result on purpose: "0 rows, no error" is a legitimate,
                // common state (nobody's done anything yet); "0 rows,
                // error set" means the request itself blew up server-
                // side and the table shown is stale/wrong, not actually
                // empty - those used to render as the exact same "No
                // activity matches these filters" message, which is
                // exactly what made this bug so hard to tell apart from
                // a real empty state.
                error: false,
            },
            // Common "what just happened" modal shown for any Recent
            // Activity / Activity Log row, instead of jumping straight
            // into the underlying record's form view.
            activityDetail: { open: false, row: null },
            activityDebug: { open: false, loading: false, data: null },
        });

        this._applyDateRange();

        onWillStart(async () => {
            await Promise.all([
                this.loadRoleProfile(),
                this.loadOverview(),
                this.loadConfig(),
                this.loadFilterOptions(),
                this.loadBranches(),
            ]);
            if (!this.state.roleProfile.tabs.some((t) => t.key === this.state.activeTab)) {
                this.state.activeTab = this.state.roleProfile.tabs[0]?.key || "overview";
            }
            this._applyDeepLink();
        });

        useEffect(
            () => this.renderCharts(),
            () => [this.state.data.sales_trend, this.state.data.purchase_trend, this.state.data.cash_flow, this.state.data.workforce, this.state.data.revenue_overview, this.state.trendChartType, this.state.loading, this.state.activeTab, this.state.view]
        );

        // Click anywhere outside a popover closes it — no need to hit
        // the trigger again to dismiss.
        useExternalListener(window, "click", (ev) => {
            if (this.state.dateSelectorOpen && this.dateSelectorRef.el && !this.dateSelectorRef.el.contains(ev.target)) {
                this.state.dateSelectorOpen = false;
            }
        }, { capture: true });
    }

    // Lets an external caller open this dashboard already jumped to a
    // specific filtered view instead of the plain Overview tab — used
    // by theme_shell's sidebar notification bell, whose "Low stock"
    // row does `doAction({ tag: "binget_dashboard", params: { explorerStatus: "low" } })`
    // rather than opening a plain list view like every other notification.
    _applyDeepLink() {
        const explorerStatus = this.props.action?.params?.explorerStatus;
        if (explorerStatus) {
            this.openInventoryStatus(explorerStatus);
        }
    }

    // ------------------------------------------------------------
    // DATA
    // ------------------------------------------------------------
    async loadRoleProfile() {
        try {
            this.state.roleProfile = await this.orm.call("binget.dashboard", "get_role_profile", []);
        } catch (e) {
            console.error("binget_dashboard: failed to load role profile", e);
        }
    }

    async loadOverview() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("binget.dashboard", "get_overview", [], {
                period: "custom",
                date_from: this.state.dateFrom || null,
                date_to: this.state.dateTo || null,
                company_id: this.state.companyId || null,
            });
        } catch (e) {
            console.error("binget_dashboard: failed to load overview", e);
        } finally {
            this.state.loading = false;
        }
    }

    async loadFilterOptions() {
        try {
            this.state.filterOptions = await this.orm.call("binget.dashboard", "get_filter_options", []);
        } catch (e) {
            console.error("binget_dashboard: failed to load filter options", e);
        }
    }

    async loadConfig() {
        try {
            this.state.config = await this.orm.call("binget.dashboard", "get_config", []);
        } catch (e) {
            console.error("binget_dashboard: failed to load configuration", e);
        }
    }

    // NOTE: notification loading/acknowledgement (get_notifications,
    // mark_notifications_seen, mark_notification_seen on binget.dashboard)
    // used to live here. That data and those RPC methods still exist
    // server-side untouched — LC Management and other modules still feed
    // into them — but the bell UI that read them now lives in theme_shell's
    // sidebar (visible on every page), so this component no longer polls
    // or renders it itself.

    async loadBranches() {
        try {
            this.state.branches = await this.orm.call("binget.dashboard", "get_inventory_branches", []);
        } catch (e) {
            console.error("binget_dashboard: failed to load branch summary", e);
        }
    }

    async saveConfigValue(key, value) {
        this.state.config[key] = value;
        try {
            await this.orm.call("binget.dashboard", "set_config", [], { key, value });
        } catch (e) {
            console.error("binget_dashboard: failed to save setting", key, e);
        }
        this.loadOverview();
    }

    // Template expressions in OWL are compiled against the component's
    // rendering context, not the global scope - a bare `parseFloat(...)`
    // written directly in a t-on-change attribute resolves to
    // `ctx['parseFloat']`, which is undefined, not the built-in
    // function ("v71 is not a function" is exactly that: the compiled
    // reference to parseFloat). So numeric settings fields pass their
    // raw string value here and let real JS (this file, not a template
    // expression) do the parsing, instead of calling parseFloat from
    // inside the XML.
    saveConfigNumber(key, rawValue, fallback) {
        const parsed = parseFloat(rawValue);
        this.saveConfigValue(key, Number.isFinite(parsed) ? parsed : fallback);
    }

    async loadExplorer(resetOffset = true) {
        if (resetOffset) this.state.explorer.offset = 0;
        this.state.explorer.loading = true;
        try {
            const res = await this.orm.call("binget.dashboard", "get_inventory_explorer", [], {
                warehouse_id: this.state.explorer.warehouseId || null,
                location_id: this.state.explorer.locationId || null,
                status: this.state.explorer.status,
                limit: this.state.explorer.limit,
                offset: this.state.explorer.offset,
            });
            this.state.explorer.rows = res.rows;
            this.state.explorer.total = res.total;
        } catch (e) {
            console.error("binget_dashboard: failed to load inventory explorer", e);
        } finally {
            this.state.explorer.loading = false;
        }
    }

    onProductLookupInput(ev) {
        const query = ev.target.value;
        this.state.productLookup.query = query;
        clearTimeout(this._productLookupTimer);
        this._productLookupTimer = setTimeout(() => this.runProductLookup(), 300);
    }

    async runProductLookup() {
        if (this.state.productLookup.query.trim().length < 2) {
            this.state.productLookup.rows = [];
            return;
        }
        this.state.productLookup.loading = true;
        try {
            const res = await this.orm.call("binget.dashboard", "get_product_availability", [], {
                query: this.state.productLookup.query,
            });
            this.state.productLookup.rows = res.rows;
        } catch (e) {
            console.error("binget_dashboard: failed to look up product availability", e);
        } finally {
            this.state.productLookup.loading = false;
        }
    }

    // ------------------------------------------------------------
    // DATE SELECTOR — a single popover replacing the old row of
    // preset buttons + native <select> elements. Always resolves to
    // either one calendar month or one full year, clamped to today.
    //
    // Uses a draft/commit split: opening the popover, or stepping the
    // year, only changes the DRAFT — nothing is applied to the actual
    // dashboard data until you explicitly click a month (or "View all
    // of <year>"). Without this, stepping the year while a month was
    // already selected silently re-applied that same month under the
    // new year, which looked like an accidental selection.
    // ------------------------------------------------------------
    // ------------------------------------------------------------
    // FORMATTING
    // ------------------------------------------------------------
    formatCompact(value) {
        const num = Number(value) || 0;
        const sign = num < 0 ? "-" : "";
        const abs = Math.abs(num);
        if (abs >= 1e9) return sign + this._trimZero((abs / 1e9).toFixed(2)) + "B";
        if (abs >= 1e6) return sign + this._trimZero((abs / 1e6).toFixed(2)) + "M";
        if (abs >= 1e3) return sign + this._trimZero((abs / 1e3).toFixed(1)) + "K";
        return sign + Math.round(abs).toLocaleString();
    }
    _trimZero(s) {
        return s.replace(/\.0+$/, "");
    }

    // Horizontal bar-list scales: largest value in each list, used to
    // size every bar relative to the top entry. Guarded against 0/empty
    // so a bar never divides by zero.
    get topCustomersMax() { return Math.max(1, ...(this.state.data.top_customers.rows || []).map((r) => r.total)); }
    get topOverdueCustomersMax() { return Math.max(1, ...(this.state.data.top_overdue_customers.rows || []).map((r) => r.total)); }
    get topProductsMax() { return Math.max(1, ...(this.state.data.top_products.rows || []).map((r) => r.total)); }
    get topVendorsMax() { return Math.max(1, ...(this.state.data.top_vendors.rows || []).map((r) => r.total)); }
    get topPurchasedProductsMax() { return Math.max(1, ...(this.state.data.top_purchased_products.rows || []).map((r) => r.total)); }

    // Health-bar segments for a branch card: proportion of OK / Low /
    // Out SKUs. A branch with zero SKUs isn't "100% healthy" - it's
    // empty, which is its own distinct state (no stock has ever moved
    // through it, so there's nothing to say is "OK") - so this returns
    // an explicit "empty" flag rather than quietly folding it into "ok".
    branchHealthPct(branch) {
        const total = branch.sku_count || 0;
        if (!total) {
            return { empty: true, ok: 0, low: 0, out: 0 };
        }
        const low = branch.low_stock || 0;
        const out = branch.out_of_stock || 0;
        const ok = Math.max(0, total - low - out);
        return { empty: false, ok: (ok / total) * 100, low: (low / total) * 100, out: (out / total) * 100 };
    }

    // KPI grid columns: capped at 4 (the admin Overview strip is 4
    // cards), but uses the actual number of visible cards when
    // there are fewer - otherwise a role with only 2 KPIs (e.g.
    // Purchase Officer) gets blank columns on a fixed grid instead
    // of both cards filling the row.
    get kpiStripColumns() {
        return Math.min(5, Math.max(1, this.state.roleProfile.visible_kpis.length));
    }

    get dateLabel() {
        if (this.state.dateScope === "year") return String(this.state.selectedYear);
        if (this.state.dateScope === "custom") {
            return `${this._formatDateShort(this.state.customFrom)} – ${this._formatDateShort(this.state.customTo)}`;
        }
        return `${MONTH_FULL[this.state.selectedMonth - 1]} ${this.state.selectedYear}`;
    }

    _formatDateShort(iso) {
        if (!iso) return "…";
        const d = new Date(`${iso}T00:00:00`);
        return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }

    toggleDateSelector() {
        this.state.dateSelectorOpen = !this.state.dateSelectorOpen;
        if (this.state.dateSelectorOpen) {
            // Seed the draft from the last committed selection.
            this.state.dateDraft.scope = this.state.dateScope;
            this.state.dateDraft.year = this.state.selectedYear;
            this.state.dateDraft.month = this.state.dateScope === "month" ? this.state.selectedMonth : null;
            this.state.dateDraft.customFrom = this.state.customFrom;
            this.state.dateDraft.customTo = this.state.customTo;
        }
    }

    setDateScope(scope) {
        this.state.dateDraft.scope = scope;
        if (scope === "month") this.state.dateDraft.month = null;
    }

    stepYear(delta) {
        const next = this.state.dateDraft.year + delta;
        if (next > new Date().getFullYear()) return;
        this.state.dateDraft.year = next;
        // Stepping the year always requires an explicit re-pick of the
        // month — it is never carried over automatically.
        this.state.dateDraft.month = null;
    }

    pickMonth(month) {
        this.state.dateDraft.month = month;
        this.state.selectedMonth = month;
        this.state.selectedYear = this.state.dateDraft.year;
        this.state.dateScope = "month";
        this._commitDateSelection();
    }

    confirmYear() {
        this.state.selectedYear = this.state.dateDraft.year;
        this.state.dateScope = "year";
        this._commitDateSelection();
    }

    get customRangeValid() {
        const { customFrom, customTo } = this.state.dateDraft;
        return !!customFrom && !!customTo && customFrom <= customTo;
    }

    confirmCustomRange() {
        if (!this.customRangeValid) return;
        this.state.customFrom = this.state.dateDraft.customFrom;
        this.state.customTo = this.state.dateDraft.customTo;
        this.state.dateScope = "custom";
        this._commitDateSelection();
    }

    _commitDateSelection() {
        this._applyDateRange();
        this.state.dateSelectorOpen = false;
        this.loadOverview();
        if (this.state.activityLog.loaded) this.loadActivityLog();
    }

    _applyDateRange() {
        const toIso = (d) => d.toISOString().slice(0, 10);
        const today = new Date();
        const todayIso = toIso(today);
        if (this.state.dateScope === "year") {
            const first = new Date(this.state.selectedYear, 0, 1);
            const last = new Date(this.state.selectedYear, 11, 31);
            this.state.dateFrom = toIso(first);
            this.state.dateTo = toIso(last > today ? today : last);
        } else if (this.state.dateScope === "custom") {
            this.state.dateFrom = this.state.customFrom;
            this.state.dateTo = this.state.customTo > todayIso ? todayIso : this.state.customTo;
        } else {
            const first = new Date(this.state.selectedYear, this.state.selectedMonth - 1, 1);
            const last = new Date(this.state.selectedYear, this.state.selectedMonth, 0);
            this.state.dateFrom = toIso(first);
            this.state.dateTo = toIso(last > today ? today : last);
        }
    }

    isCurrentMonth(month) {
        const today = new Date();
        return this.state.dateDraft.year === today.getFullYear() && month === today.getMonth() + 1;
    }
    isFutureMonth(month) {
        const today = new Date();
        return this.state.dateDraft.year === today.getFullYear() && month > today.getMonth() + 1;
    }

    // ------------------------------------------------------------
    // UI EVENTS
    // ------------------------------------------------------------
    setTab(key) {
        this.state.activeTab = key;
        // Always refetch on opening the Activity tab, rather than only
        // the first time this session (the old `!loaded` guard). This
        // tab is meant to be a live audit trail - caching it stale
        // across tab switches led to exactly the kind of confusing
        // mismatch we saw: 1 row showing on the Overview widget (which
        // always reloads fresh) but 0 on this tab, for the very same
        // user, because this tab still held whatever it fetched the
        // very first time it was opened that session, before newer
        // activity existed yet. `loaded` is now only used to decide
        // whether the (admin-only) user filter list still needs a
        // one-time fetch, not to skip refetching the rows themselves.
        if (key === "activity") {
            const firstOpen = !this.state.activityLog.loaded;
            this.state.activityLog.loaded = true;
            this.loadActivityLog();
            if (firstOpen && this.state.roleProfile.is_admin) this.loadActivityUsers();
        }
    }

    onCompanyChange() {
        this.loadOverview();
        this.loadBranches();
        if (this.state.activityLog.loaded) this.loadActivityLog();
    }

    setTrendChartType(type) {
        this.state.trendChartType = type;
    }

    toggleConfig() {
        this.state.showConfig = !this.state.showConfig;
    }

    // ------------------------------------------------------------
    // BRANCH — a dedicated full page, not a modal, so it feels like
    // real navigation rather than a popup interrupting the dashboard.
    // ------------------------------------------------------------
    async openBranchDetail(branch) {
        this.state.view = "branch";
        this.state.branchDetail.loading = true;
        this.state.branchDetail.data = null;
        this.state.branchDetail.showInventory = false;
        this.state.branchDetail.explorer.rows = [];
        this.state.branchDetail.explorer.offset = 0;
        this.state.branchDetail.explorer.status = "all";
        try {
            this.state.branchDetail.data = await this.orm.call("binget.dashboard", "get_branch_detail", [], {
                warehouse_id: branch.id,
            });
        } catch (e) {
            console.error("binget_dashboard: failed to load branch detail", e);
        } finally {
            this.state.branchDetail.loading = false;
        }
    }

    backToDashboard() {
        this.state.view = "main";
    }

    // "Browse full inventory" now expands a product list right here on
    // the branch page instead of routing away to the Inventory tab.
    viewBranchFullInventory() {
        this.state.branchDetail.showInventory = !this.state.branchDetail.showInventory;
        if (this.state.branchDetail.showInventory && !this.state.branchDetail.explorer.rows.length) {
            this.loadBranchExplorer();
        }
    }

    async loadBranchExplorer(resetOffset = true) {
        const wid = this.state.branchDetail.data && this.state.branchDetail.data.id;
        if (!wid) return;
        if (resetOffset) this.state.branchDetail.explorer.offset = 0;
        this.state.branchDetail.explorer.loading = true;
        try {
            const res = await this.orm.call("binget.dashboard", "get_inventory_explorer", [], {
                warehouse_id: wid,
                location_id: this.state.branchDetail.explorer.locationId || null,
                status: this.state.branchDetail.explorer.status,
                limit: this.state.branchDetail.explorer.limit,
                offset: this.state.branchDetail.explorer.offset,
            });
            this.state.branchDetail.explorer.rows = res.rows;
            this.state.branchDetail.explorer.total = res.total;
        } catch (e) {
            console.error("binget_dashboard: failed to load branch inventory", e);
        } finally {
            this.state.branchDetail.explorer.loading = false;
        }
    }

    setBranchExplorerStatus(status) {
        this.state.branchDetail.explorer.status = status;
        this.loadBranchExplorer();
    }

    branchExplorerNextPage() {
        const ex = this.state.branchDetail.explorer;
        if (ex.offset + ex.limit < ex.total) {
            ex.offset += ex.limit;
            this.loadBranchExplorer(false);
        }
    }

    branchExplorerPrevPage() {
        const ex = this.state.branchDetail.explorer;
        if (ex.offset > 0) {
            ex.offset -= ex.limit;
            this.loadBranchExplorer(false);
        }
    }

    toggleExplorer() {
        this.state.explorer.expanded = !this.state.explorer.expanded;
        if (this.state.explorer.expanded && !this.state.explorer.rows.length) {
            this.loadExplorer();
        }
    }

    explorerNextPage() {
        if (this.state.explorer.offset + this.state.explorer.limit < this.state.explorer.total) {
            this.state.explorer.offset += this.state.explorer.limit;
            this.loadExplorer(false);
        }
    }

    explorerPrevPage() {
        if (this.state.explorer.offset > 0) {
            this.state.explorer.offset -= this.state.explorer.limit;
            this.loadExplorer(false);
        }
    }

    // ------------------------------------------------------------
    // ACTIVITY LOG — full searchable/filterable history, as opposed to
    // the short Recent Activity widget on Overview/Operations. Scoped
    // to the selected date range and branch, same as the rest of the
    // dashboard.
    // ------------------------------------------------------------
    async loadActivityLog(resetOffset = true) {
        const log = this.state.activityLog;
        if (resetOffset) log.offset = 0;
        log.loading = true;
        log.error = false;
        try {
            const res = await this.orm.call("binget.dashboard", "get_activity_log", [], {
                type_filter: log.typeFilter,
                user_id: log.userId || null,
                search: log.search || null,
                date_from: this.state.dateFrom || null,
                date_to: this.state.dateTo || null,
                company_id: this.state.companyId || null,
                limit: log.limit,
                offset: log.offset,
            });
            log.rows = res.rows;
            log.total = res.total;
        } catch (e) {
            console.error("binget_dashboard: failed to load activity log", e);
            // Previously left `rows`/`total` untouched on failure, so
            // the table just showed "No activity matches these
            // filters" - indistinguishable from a real empty result.
            // Now it's explicit: the request failed, here's nothing
            // to trust on screen, try again.
            log.rows = [];
            log.total = 0;
            log.error = true;
        } finally {
            log.loading = false;
        }
    }

    async loadActivityUsers() {
        try {
            const res = await this.orm.call("binget.dashboard", "get_activity_users", []);
            this.state.activityLog.users = res.rows;
        } catch (e) {
            console.error("binget_dashboard: failed to load activity users", e);
        }
    }

    setActivityType(type) {
        this.state.activityLog.typeFilter = type;
        this.loadActivityLog();
    }

    onActivityUserChange(ev) {
        this.state.activityLog.userId = ev.target.value;
        this.loadActivityLog();
    }

    onActivitySearchInput(ev) {
        this.state.activityLog.search = ev.target.value;
        clearTimeout(this._activitySearchTimer);
        this._activitySearchTimer = setTimeout(() => this.loadActivityLog(), 350);
    }

    activityNextPage() {
        const log = this.state.activityLog;
        if (log.offset + log.limit < log.total) {
            log.offset += log.limit;
            this.loadActivityLog(false);
        }
    }

    activityPrevPage() {
        const log = this.state.activityLog;
        if (log.offset > 0) {
            log.offset -= log.limit;
            this.loadActivityLog(false);
        }
    }

    // Exports whatever is currently filtered in the Activity Log as a
    // PDF — same query, just uncapped rather than paginated. Admin-only,
    // enforced both here (button hidden) and server-side in
    // _get_report_values (so it can't be triggered by editing the DOM).
    async exportActivityPdf() {
        const log = this.state.activityLog;
        const context = {
            binget_activity_type_filter: log.typeFilter,
            binget_activity_user_id: log.userId || null,
            binget_activity_search: log.search || null,
            binget_activity_date_from: this.state.dateFrom || null,
            binget_activity_date_to: this.state.dateTo || null,
            binget_activity_company_id: this.state.companyId || null,
        };
        try {
            await this.action.doAction("binget_dashboard.action_report_activity_log", { additionalContext: context });
        } catch (e) {
            console.error("binget_dashboard: failed to export activity PDF", e);
        }
    }

    // ------------------------------------------------------------
    // DRILL-DOWN NAVIGATION
    // ------------------------------------------------------------
    _openList(resModel, name, domain) {
        this.action.doAction({
            type: "ir.actions.act_window", name, res_model: resModel,
            views: [[false, "list"], [false, "form"]], domain, target: "current",
        });
    }

    _openForm(resModel, resId) {
        if (!resId) return;
        this.action.doAction({
            type: "ir.actions.act_window", res_model: resModel, res_id: resId,
            views: [[false, "form"]], target: "current",
        });
    }

    openOpenOrders() {
        this._openList("sale.order", "Open Sales Orders", [["state", "in", ["draft", "sent"]]]);
    }
    // Clicking the Total Revenue tile used to jump to a separate list
    // view. It now just scrolls down to the Revenue Overview chart
    // that's already on this same page — no page navigation needed.
    // That chart only renders for admins/accounting (see the xml), so
    // this falls back to the old list view for anyone else who can
    // still see the tile (e.g. Sales) but not that card.
    openRevenueReport() {
        if (this.revenueOverviewCardRef.el) {
            this.state.activeTab = "overview";
            this._scrollToRef(this.revenueOverviewCardRef);
            return;
        }
        this._openList("sale.order", "Revenue — Confirmed Orders", [["state", "in", ["sale", "done"]]]);
    }
    openOverdueInvoices() {
        this._openList("account.move", "Overdue Invoices", [
            ["move_type", "=", "out_invoice"], ["state", "=", "posted"],
            ["payment_state", "not in", ["paid", "in_payment", "reversed"]],
            ["invoice_date_due", "<", new Date().toISOString().slice(0, 10)],
        ]);
    }
    openOutstandingReceivables() {
        this._openList("account.move", "Outstanding Receivables", [
            ["move_type", "=", "out_invoice"], ["state", "=", "posted"], ["payment_state", "not in", ["paid", "in_payment", "reversed"]],
        ]);
    }
    openOutstandingPayables() {
        this._openList("account.move", "Outstanding Payables", [
            ["move_type", "=", "in_invoice"], ["state", "=", "posted"], ["payment_state", "not in", ["paid", "in_payment", "reversed"]],
        ]);
    }
    openInventoryStatus(status) {
        this.state.view = "main";
        this.state.activeTab = "inventory";
        this.state.explorer.expanded = true;
        this.state.explorer.status = status;
        this.state.explorer.warehouseId = "";
        this.loadExplorer();
        // The KPI card already did its job (the explorer below is now
        // filtered) - but if it's off-screen, that's invisible and just
        // looks like the click did nothing. Scroll it into view once
        // the DOM has actually updated with the expanded card.
        this._scrollToRef(this.explorerCardRef);
    }

    // Waits a couple of animation frames (cheap, reliable way to let
    // Owl finish patching the DOM after a state change) before
    // scrolling an element into view, so this works whether the target
    // was already rendered or just got expanded/created this click.
    _scrollToRef(ref) {
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                ref.el?.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        });
    }
    // Kept as a thin alias: still used directly by this dashboard's own
    // KPI cards/Explorer, and by name ("openLowStock") by theme_shell's
    // sidebar notification bell — renaming would silently break that.
    openLowStock() {
        this.openInventoryStatus("low");
    }
    openExplorerAll() {
        this.openInventoryStatus("all");
    }
    openProcurement(states) {
        this._openList("purchase.order", "Purchase Orders", [["state", "in", states]]);
    }
    openPendingPurchases() {
        this.openProcurement(["sent", "to approve"]);
    }
    // Also called by name ("openOrdersReadyToInvoice") from theme_shell's
    // sidebar notification bell — see get_notifications() in dashboard.py
    // for the backend action string this must keep matching.
    openOrdersReadyToInvoice() {
        this._openList("sale.order", "Sales Orders Ready to Invoice", [
            ["state", "=", "sale"], ["invoice_status", "=", "to invoice"],
        ]);
    }
    openPartner(id) { this._openForm("res.partner", id); }
    openProduct(id) { this._openForm("product.product", id); }
    // Shows the "what just happened" modal for a Recent Activity /
    // Activity Log row instead of jumping straight to the underlying
    // record's form view - keeps people on the dashboard while still
    // giving them everything the row itself tells you. The record is
    // still one click away from inside the modal for anyone who wants
    // to dig further.
    openActivityRecord(row) {
        this.state.activityDetail = { open: true, row };
    }

    closeActivityDetail() {
        this.state.activityDetail.open = false;
    }

    openActivityDetailRecord() {
        const row = this.state.activityDetail.row;
        if (!row || row.action === "deleted") return;
        this.state.activityDetail.open = false;
        this._openForm(row.model, row.res_id);
    }

    async runActivityDebug() {
        const userId = this.state.activityLog.userId;
        if (!userId) return;
        this.state.activityDebug.open = true;
        this.state.activityDebug.loading = true;
        this.state.activityDebug.data = null;
        try {
            this.state.activityDebug.data = await this.orm.call("binget.dashboard", "get_activity_debug", [], {
                user_id: userId,
                date_from: this.state.dateFrom || null,
                date_to: this.state.dateTo || null,
                company_id: this.state.companyId || null,
            });
        } catch (e) {
            console.error("binget_dashboard: activity debug failed", e);
            this.state.activityDebug.open = false;
        } finally {
            this.state.activityDebug.loading = false;
        }
    }

    closeActivityDebug() {
        this.state.activityDebug.open = false;
    }
    openEmployees() { this._openList("hr.employee", "Employees", [["active", "=", true]]); }
    openTimeOff() { this._openList("hr.leave", "Pending Time Off", [["state", "in", ["confirm", "validate1"]]]); }
    openLCAccountRequests() {
        this._openList("lc.account.setup.request", "LC Account Setup Requests", [["state", "!=", "completed"]]);
    }
    openLCPaymentRequests() {
        this._openList("lc.settlement.line", "LC Payment Requests", [["state", "=", "submitted"]]);
    }
    openLCOpeningRequests() {
        this._openList("lc.management", "LC Opening Requests", [["state", "=", "pending_approval"]]);
    }
    openManufacturingInProgress() { this._openList("mrp.production", "Manufacturing Orders", [["state", "=", "progress"]]); }

    // ------------------------------------------------------------
    // CHARTS
    // ------------------------------------------------------------
    renderCharts() {
        if (this.state.loading || this.state.view !== "main") return;
        this.renderTrendChart();
        this.renderPurchaseTrendChart();
        this.renderAgingChart();
        this.renderEmployeeGrowthChart();
        this.renderDepartmentPieChart();
        this.renderRevenueOverviewChart();
    }

    renderTrendChart() {
        if (!this.trendChartRef.el || typeof Chart === "undefined") return;
        if (this.trendChartInstance) this.trendChartInstance.destroy();
        const rootStyles = getComputedStyle(document.body);
        const accent = rootStyles.getPropertyValue("--sb-accent").trim() || "#ba7517";
        const textDim = rootStyles.getPropertyValue("--sb-text-dim").trim() || "#666";
        const rows = this.state.data.sales_trend.rows || [];
        this.trendChartInstance = new Chart(this.trendChartRef.el, {
            type: this.state.trendChartType,
            data: {
                labels: rows.map((r) => r.label),
                datasets: [{
                    label: "Sales", data: rows.map((r) => r.total), borderColor: accent,
                    backgroundColor: `${accent}33`, fill: this.state.trendChartType === "line",
                    tension: 0.35, borderWidth: 2.5,
                    pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: accent,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                animation: { duration: 700, easing: "easeOutQuart" },
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: textDim }, grid: { display: false } },
                    y: { ticks: { color: textDim }, grid: { color: "rgba(0,0,0,0.05)" } },
                },
            },
        });
    }

    renderPurchaseTrendChart() {
        if (!this.purchaseTrendChartRef.el || typeof Chart === "undefined") return;
        if (this.purchaseTrendChartInstance) this.purchaseTrendChartInstance.destroy();
        const rootStyles = getComputedStyle(document.body);
        const accent = rootStyles.getPropertyValue("--sb-accent").trim() || "#ba7517";
        const textDim = rootStyles.getPropertyValue("--sb-text-dim").trim() || "#666";
        const rows = this.state.data.purchase_trend.rows || [];
        this.purchaseTrendChartInstance = new Chart(this.purchaseTrendChartRef.el, {
            type: this.state.trendChartType,
            data: {
                labels: rows.map((r) => r.label),
                datasets: [{
                    label: "Purchases", data: rows.map((r) => r.total), borderColor: accent,
                    backgroundColor: `${accent}33`, fill: this.state.trendChartType === "line",
                    tension: 0.35, borderWidth: 2.5,
                    pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: accent,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                animation: { duration: 700, easing: "easeOutQuart" },
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: textDim }, grid: { display: false } },
                    y: { ticks: { color: textDim }, grid: { color: "rgba(0,0,0,0.05)" } },
                },
            },
        });
    }

    renderAgingChart() {
        if (!this.agingChartRef.el || typeof Chart === "undefined") return;
        if (this.agingChartInstance) this.agingChartInstance.destroy();
        const rootStyles = getComputedStyle(document.body);
        const textDim = rootStyles.getPropertyValue("--sb-text-dim").trim() || "#666";
        const buckets = this.state.data.cash_flow.ar_aging || [];
        const colors = ["#4caf50", "#d6961d", "#e08a2e", "#c9502e", "#a83232"];
        this.agingChartInstance = new Chart(this.agingChartRef.el, {
            type: "bar",
            data: { labels: buckets.map((b) => b.label), datasets: [{ data: buckets.map((b) => b.amount), backgroundColor: colors, borderRadius: 6 }] },
            options: {
                responsive: true, maintainAspectRatio: false,
                animation: { duration: 700, easing: "easeOutQuart" },
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: textDim }, grid: { display: false } },
                    y: { ticks: { color: textDim }, grid: { color: "rgba(0,0,0,0.05)" } },
                },
            },
        });
    }

    // "Employee Growth" — cumulative active headcount over the last 6
    // months, same visual language as Sales Trend so it reads as
    // familiar rather than a bolted-on afterthought.
    renderEmployeeGrowthChart() {
        if (!this.employeeGrowthChartRef.el || typeof Chart === "undefined") return;
        if (this.employeeGrowthChartInstance) this.employeeGrowthChartInstance.destroy();
        const rootStyles = getComputedStyle(document.body);
        const accent = rootStyles.getPropertyValue("--sb-accent").trim() || "#ba7517";
        const textDim = rootStyles.getPropertyValue("--sb-text-dim").trim() || "#666";
        const rows = (this.state.data.workforce && this.state.data.workforce.employee_growth) || [];
        this.employeeGrowthChartInstance = new Chart(this.employeeGrowthChartRef.el, {
            type: "line",
            data: {
                labels: rows.map((r) => r.label),
                datasets: [{
                    label: "Headcount", data: rows.map((r) => r.count), borderColor: accent,
                    backgroundColor: `${accent}33`, fill: true,
                    tension: 0.35, borderWidth: 2.5,
                    pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: accent,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                animation: { duration: 700, easing: "easeOutQuart" },
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: textDim }, grid: { display: false } },
                    y: { ticks: { color: textDim, precision: 0 }, grid: { color: "rgba(0,0,0,0.05)" }, beginAtZero: true },
                },
            },
        });
    }

    // "Department Distribution" — active headcount by department, as a
    // donut so the total (already shown as the Active Employees KPI)
    // isn't duplicated awkwardly inside the chart itself.
    renderDepartmentPieChart() {
        if (!this.departmentPieChartRef.el || typeof Chart === "undefined") return;
        if (this.departmentPieChartInstance) this.departmentPieChartInstance.destroy();
        const rows = (this.state.data.workforce && this.state.data.workforce.department_distribution) || [];
        const palette = ["#ba7517", "#4caf50", "#3d7ba8", "#a83232", "#8a5fb0", "#d6961d", "#2e8f8f", "#6b6b6b"];
        this.departmentPieChartInstance = new Chart(this.departmentPieChartRef.el, {
            type: "doughnut",
            data: {
                labels: rows.map((r) => r.label),
                datasets: [{ data: rows.map((r) => r.count), backgroundColor: rows.map((_, i) => palette[i % palette.length]), borderWidth: 2, borderColor: "#fff" }],
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: "62%",
                animation: { duration: 700, easing: "easeOutQuart" },
                plugins: { legend: { position: "right", labels: { boxWidth: 12, padding: 12 } } },
            },
        });
    }
    // "Revenue Overview" — Revenue (posted customer invoices) as bars
    // against Expenses (posted vendor bills) as an overlaid line, one
    // point per month for the current year. Lives in the accounting
    // section since it's a P&L-style view, not a sales pipeline one.
    renderRevenueOverviewChart() {
        if (!this.revenueOverviewChartRef.el || typeof Chart === "undefined") return;
        if (this.revenueOverviewChartInstance) this.revenueOverviewChartInstance.destroy();
        const rootStyles = getComputedStyle(document.body);
        const accent = rootStyles.getPropertyValue("--sb-accent").trim() || "#ba7517";
        const textDim = rootStyles.getPropertyValue("--sb-text-dim").trim() || "#666";
        const expenseColor = "#8a93a3";
        const data = this.state.data.revenue_overview || { labels: [], revenue: [], expenses: [] };
        this.revenueOverviewChartInstance = new Chart(this.revenueOverviewChartRef.el, {
            data: {
                labels: data.labels,
                datasets: [
                    {
                        type: "bar", label: "Revenue", data: data.revenue,
                        backgroundColor: accent, borderRadius: 5, maxBarThickness: 30, order: 2,
                    },
                    {
                        type: "line", label: "Expenses", data: data.expenses,
                        borderColor: expenseColor, backgroundColor: "transparent",
                        tension: 0.35, borderWidth: 2.5, pointRadius: 3, pointHoverRadius: 5,
                        pointBackgroundColor: expenseColor, order: 1,
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                animation: { duration: 700, easing: "easeOutQuart" },
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => ` ${ctx.dataset.label}: ${this.formatCompact(ctx.parsed.y)}`,
                        },
                    },
                },
                scales: {
                    x: { ticks: { color: textDim }, grid: { display: false } },
                    y: { ticks: { color: textDim, callback: (v) => this.formatCompact(v) }, grid: { color: "rgba(0,0,0,0.05)" }, beginAtZero: true },
                },
            },
        });
    }
}

registry.category("actions").add("binget_dashboard", BingetDashboard);
