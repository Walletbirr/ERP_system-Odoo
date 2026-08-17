/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted, onPatched, onWillUnmount } from "@odoo/owl";

// ── Formatters ────────────────────────────────────────────────────────────────

function fmt(n, decimals = 0) {
    if (n === null || n === undefined || isNaN(Number(n))) return "0";
    const num = parseFloat(n);
    if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + "M";
    if (num >= 1_000)     return (num / 1_000).toFixed(1) + "K";
    return num.toFixed(decimals);
}

function fmtCur(n) { return "ETB " + fmt(n, 2); }

const PALETTE = [
    "#7c5c2e","#a07840","#c49c6c","#e8c89a",
    "#28a745","#007bff","#fd7e14","#dc3545",
    "#6f42c1","#20c997","#17a2b8","#ffc107",
];

// ── Dashboard Component ───────────────────────────────────────────────────────

export class BhManagementDashboard extends Component {

    setup() {
        this.notification = useService("notification");

        const today    = new Date();
        // Default: 1st of current month -> today (captures all current-month data)
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1)
                            .toISOString().split("T")[0];
        const todayStr = today.toISOString().split("T")[0];

        this.state = useState({
            loading:          true,
            activeTab:        "sales",
            data:             null,
            dateFrom:         firstDay,
            dateTo:           todayStr,
            error:            null,
            selectedPeriod:   "this_month",
            periods:          [],
            periodsLoading:   false,
        });

        this.charts         = {};
        this._pendingRender = false;

        onMounted(async () => {
            await this._loadPeriods();
            this.loadData();
        });

        // onPatched fires after every OWL re-render — use it to draw charts
        onPatched(() => {
            if (!this.state.loading && this.state.data && !this._pendingRender) {
                this._pendingRender = true;
                requestAnimationFrame(() => {
                    this._renderCharts();
                    this._pendingRender = false;
                });
            }
        });

        onWillUnmount(() => this._destroyCharts());
    }

    // ── Data ──────────────────────────────────────────────────────────────────

    async loadData() {
        this.state.loading = true;
        this.state.error   = null;
        this._destroyCharts();
        try {
            const response = await fetch("/bh_dashboard/get_data", {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    id:      1,
                    method:  "call",
                    params: {
                        date_from: this.state.dateFrom,
                        date_to:   this.state.dateTo,
                    },
                }),
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const json = await response.json();

            if (json.error) {
                throw new Error(json.error.data?.message || json.error.message || "Server error");
            }

            const data = json.result;
            if (!data) throw new Error("No data returned from server");

            this.state.data    = data;
            this.state.loading = false;
            // onPatched will handle chart rendering after DOM update

        } catch (e) {
            console.error("BH Dashboard error:", e);
            this.state.error   = e.message || "Unknown error";
            this.state.loading = false;
        }
    }

    // ── Tab & Sidebar handlers ────────────────────────────────────────────────

    setTabSales()         { this._setTab("sales"); }
    setTabInventory()     { this._setTab("inventory"); }
    setTabFinance()       { this._setTab("finance"); }
    setTabPurchase()      { this._setTab("purchase"); }
    setTabManufacturing() { this._setTab("manufacturing"); }
    setTabHr()            { this._setTab("hr"); }

    _setTab(tab) {
        if (this.state.activeTab === tab) return;
        this._destroyCharts();
        this.state.activeTab = tab;
        // onPatched fires after the DOM updates, drawing charts at correct size
    }

    onDateFromChange(ev) { this.state.dateFrom = ev.target.value; this.state.selectedPeriod = "custom"; }
    onDateToChange(ev)   { this.state.dateTo   = ev.target.value; this.state.selectedPeriod = "custom"; }
    onRefresh()          { this.loadData(); }

    // ── Period selector ───────────────────────────────────────────────────────

    async _loadPeriods() {
        // Built-in presets — always available, no OCA dependency needed
        const t = new Date();
        const y = t.getFullYear();
        const m = t.getMonth(); // 0-based

        const iso = d => d.toISOString().split("T")[0];
        const firstOf = (year, mo) => new Date(year, mo, 1);
        const lastOf  = (year, mo) => new Date(year, mo + 1, 0);

        const presets = [
            { key: "this_month",    label: "This Month",
              date_start: iso(firstOf(y, m)),         date_end: iso(lastOf(y, m)) },
            { key: "last_month",    label: "Last Month",
              date_start: iso(firstOf(y, m - 1)),     date_end: iso(lastOf(y, m - 1)) },
            { key: "this_quarter",  label: "This Quarter",
              date_start: iso(firstOf(y, Math.floor(m / 3) * 3)),
              date_end:   iso(lastOf(y,  Math.floor(m / 3) * 3 + 2)) },
            { key: "last_quarter",  label: "Last Quarter",
              date_start: iso(firstOf(y, Math.floor(m / 3) * 3 - 3)),
              date_end:   iso(lastOf(y,  Math.floor(m / 3) * 3 - 1)) },
            { key: "this_year",     label: "This Year",
              date_start: iso(firstOf(y, 0)),         date_end: iso(lastOf(y, 11)) },
            { key: "last_year",     label: "Last Year",
              date_start: iso(firstOf(y - 1, 0)),     date_end: iso(lastOf(y - 1, 11)) },
            { key: "last_30",       label: "Last 30 Days",
              date_start: iso(new Date(t - 30 * 86400000)), date_end: iso(t) },
            { key: "last_90",       label: "Last 90 Days",
              date_start: iso(new Date(t - 90 * 86400000)), date_end: iso(t) },
            { key: "last_6months",  label: "Last 6 Months",
              date_start: iso(firstOf(y, m - 5)),     date_end: iso(t) },
        ];

        // Also try to fetch date.range records from Odoo if the module is installed
        try {
            const res = await fetch("/web/dataset/call_kw", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    jsonrpc: "2.0", id: 1, method: "call",
                    params: {
                        model: "date.range",
                        method: "search_read",
                        args: [[["active", "=", true]]],
                        kwargs: {
                            fields: ["id", "name", "date_start", "date_end"],
                            order:  "date_start desc",
                            limit:  30,
                        },
                    },
                }),
            });
            const json = await res.json();
            if (json.result && json.result.length) {
                const oca = json.result.map(r => ({
                    key:        "oca_" + r.id,
                    label:      r.name,
                    date_start: r.date_start,
                    date_end:   r.date_end,
                }));
                this.state.periods = [
                    { key: "__sep_preset__", label: "── Quick Presets ──", date_start: null, date_end: null },
                    ...presets,
                    { key: "__sep_oca__", label: "── Fiscal / Custom Periods ──", date_start: null, date_end: null },
                    ...oca,
                    { key: "custom", label: "Custom Range", date_start: null, date_end: null },
                ];
                return;
            }
        } catch (_) { /* date.range not installed — silently fall through */ }

        // Fallback: presets only
        this.state.periods = [
            ...presets,
            { key: "custom", label: "Custom Range", date_start: null, date_end: null },
        ];
    }

    onPeriodChange(ev) {
        const key = ev.target.value;
        // Separator options: ignore
        if (key.startsWith("__sep")) return;
        this.state.selectedPeriod = key;
        if (key === "custom") return; // let user fill From/To manually
        const p = this.state.periods.find(p => p.key === key);
        if (p && p.date_start && p.date_end) {
            this.state.dateFrom = p.date_start;
            this.state.dateTo   = p.date_end;
            this.loadData(); // auto-refresh on period select
        }
    }

    // ── Chart helpers ─────────────────────────────────────────────────────────

    _destroyCharts() {
        Object.values(this.charts).forEach(c => { try { c.destroy(); } catch (_) {} });
        this.charts = {};
    }

    _ctx(id) {
        const el = document.getElementById(id);
        return el ? el.getContext("2d") : null;
    }

    _mkChart(id, config) {
        if (!window.Chart) { console.warn("Chart.js not loaded"); return; }
        const el = document.getElementById(id);
        if (!el) { console.warn("Canvas not found:", id); return; }
        if (this.charts[id]) { this.charts[id].destroy(); delete this.charts[id]; }
        // Ensure canvas has proper dimensions
        const parent = el.parentElement;
        if (parent && !el.style.height) {
            const h = config.type === "doughnut" ? 260 : 240;
            el.style.height = h + "px";
        }
        this.charts[id] = new window.Chart(el.getContext("2d"), config);
    }

    _bar(id, labels, datasets) {
        this._mkChart(id, {
            type: "bar",
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "top", labels: { font: { size: 11 } } } },
                scales: {
                    y: { beginAtZero: true, grid: { color: "#f0f0f0" } },
                    x: { grid: { display: false } },
                },
            },
        });
    }

    _line(id, labels, datasets, extraScales = {}) {
        this._mkChart(id, {
            type: "line",
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "top", labels: { font: { size: 11 } } } },
                elements: { line: { tension: 0.4 }, point: { radius: 4 } },
                scales: {
                    y: { beginAtZero: true, grid: { color: "#f0f0f0" } },
                    x: { grid: { display: false } },
                    ...extraScales,
                },
            },
        });
    }

    _pie(id, labels, data) {
        this._mkChart(id, {
            type: "doughnut",
            data: {
                labels,
                datasets: [{ data, backgroundColor: PALETTE, borderWidth: 2, borderColor: "#fff" }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "right", labels: { font: { size: 11 }, padding: 12 } } },
            },
        });
    }

    // ── Section renderers ─────────────────────────────────────────────────────

    _renderCharts() {
        if (!this.state.data) return;
        const { data, activeTab } = this.state;
        if (activeTab === "sales")         this._salesCharts(data.sales);
        if (activeTab === "inventory")     this._invCharts(data.inventory);
        if (activeTab === "finance")       this._finCharts(data.finance);
        if (activeTab === "purchase")      this._poCharts(data.purchase);
        if (activeTab === "manufacturing") this._mrpCharts(data.manufacturing);
        if (activeTab === "hr")            this._hrCharts(data.hr);
    }

    _salesCharts(s) {
        if (!s) return;
        const months   = (s.monthly_trend || []).map(r => r.month);
        const revenues = (s.monthly_trend || []).map(r => parseFloat(r.revenue || 0));
        const orders   = (s.monthly_trend || []).map(r => parseInt(r.orders   || 0));
        this._line("chart-sales-trend", months, [
            { label: "Revenue (ETB)", data: revenues, borderColor: "#7c5c2e", backgroundColor: "rgba(124,92,46,0.1)", fill: true },
            { label: "Orders",        data: orders,   borderColor: "#28a745", backgroundColor: "rgba(40,167,69,0.1)",  fill: true, yAxisID: "y2" },
        ], { y2: { beginAtZero: true, position: "right", grid: { display: false } } });

        const cn = (s.top_customers || []).map(c => c.customer);
        const cv = (s.top_customers || []).map(c => parseFloat(c.total || 0));
        this._bar("chart-top-customers", cn, [
            { label: "Revenue (ETB)", data: cv, backgroundColor: PALETTE.slice(0, cv.length) },
        ]);
    }

    _invCharts(s) {
        if (!s) return;
        const locs = (s.by_location || []).map(r => r.location.split("/").pop());
        this._bar("chart-inv-location", locs, [
            { label: "Stock Value (ETB)", data: (s.by_location || []).map(r => parseFloat(r.value || 0)), backgroundColor: PALETTE },
        ]);
        this._pie("chart-inv-pie", locs, (s.by_location || []).map(r => parseFloat(r.qty || 0)));
    }

    _finCharts(s) {
        if (!s) return;
        const months   = (s.monthly_trend || []).map(r => r.month);
        const invoiced = (s.monthly_trend || []).map(r => parseFloat(r.invoiced || 0));
        const bills    = (s.monthly_trend || []).map(r => parseFloat(r.bills    || 0));
        this._bar("chart-finance-trend", months, [
            { label: "Invoiced (ETB)", data: invoiced, backgroundColor: "rgba(40,167,69,0.7)" },
            { label: "Bills (ETB)",    data: bills,    backgroundColor: "rgba(220,53,69,0.7)" },
        ]);
        this._pie("chart-finance-pie",
            ["Receivable", "Payable"],
            [parseFloat(s.summary.total_receivable || 0), parseFloat(s.summary.total_payable || 0)]
        );
    }

    _poCharts(s) {
        if (!s) return;
        const vn = (s.top_vendors || []).map(v => v.vendor);
        const vv = (s.top_vendors || []).map(v => parseFloat(v.total || 0));
        this._bar("chart-purchase-vendors", vn, [
            { label: "Total Spent (ETB)", data: vv, backgroundColor: PALETTE.slice(0, vv.length) },
        ]);
    }

    _mrpCharts(s) {
        if (!s) return;
        this._pie("chart-mrp-status",
            ["Completed", "In Progress", "Planned"],
            [parseInt(s.summary.completed || 0), parseInt(s.summary.in_progress || 0), parseInt(s.summary.planned || 0)]
        );
        this._bar("chart-mrp-products",
            (s.by_product || []).map(r => r.product),
            [{ label: "Qty Produced", data: (s.by_product || []).map(r => parseFloat(r.produced || 0)), backgroundColor: PALETTE }]
        );
    }

    _hrCharts(s) {
        if (!s) return;
        this._bar("chart-hr-dept",
            (s.by_department || []).map(r => r.department),
            [{ label: "Employees", data: (s.by_department || []).map(r => parseInt(r.count || 0)), backgroundColor: PALETTE }]
        );
        this._pie("chart-hr-gender",
            ["Male", "Female"],
            [parseInt(s.summary.male_count || 0), parseInt(s.summary.female_count || 0)]
        );
    }
}

// ── Template ──────────────────────────────────────────────────────────────────
// Moved out of this file into static/src/xml/dashboard.xml as a named QWeb/Owl
// template ("bh_management_dashboard.Dashboard") instead of the inline `xml`
// tagged-template-literal this used to be assigned directly to
// BhManagementDashboard.template. A literal template like that has no stable
// name another addon's assets can target, so extending it (e.g. adding a new
// tab) meant either editing this file directly or copy-pasting the entire
// ~400-line template into another module just to change a few lines.
//
// A named template can be extended the normal Odoo way instead - see
// sale_credit_approval/static/src/xml/dashboard_approvals.xml for a real
// example: it adds an "Approvals" tab via
// <t t-inherit="bh_management_dashboard.Dashboard" t-inherit-mode="extension">
// + <xpath>, without touching this file at all.
BhManagementDashboard.template = "bh_management_dashboard.Dashboard";


Object.assign(BhManagementDashboard.prototype, { fmt, fmtCur });

registry.category("actions").add("bh_management_dashboard", BhManagementDashboard);
