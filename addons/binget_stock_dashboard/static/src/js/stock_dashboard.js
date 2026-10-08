/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { useImportCog } from "./import_cog";

const { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } = owl;

class BingetStockDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        // Settings cog → Import records (stock quantities, same as standard Odoo)
        this.cog = useImportCog({
            model: "stock.quant",
            context: { inventory_mode: true },
        });

        this.state = useState({
            loading: true,
            view: "overview",
            data: null,
            categories: [],
            currentWarehouseId: 0,
            currentWarehouseName: "All Warehouses",
            search: "",
            categoryId: false,
            status: "all",
            page: 1,
            pageSize: 12,
            detail: null,
            detailLoading: false,
            animKey: 0,
            // serial / lot expansion
            expandedId: null,
            unitsLoading: false,
            units: null,
        });

        onWillStart(async () => {
            await this.loadOverview();
            this.state.categories = await this.orm.call(
                "binget.stock.dashboard", "get_categories", []
            );
        });

        onMounted(() => {
            this._tiltRoot = this.rootRef.el;
            if (!this._tiltRoot) return;
            this._onTiltMove = (ev) => {
                const card = ev.target.closest(".o_binget_wh_card, .o_binget_kpi_card");
                if (!card || !this._tiltRoot.contains(card)) return;
                const r = card.getBoundingClientRect();
                const px = (ev.clientX - r.left) / r.width - 0.5;
                const py = (ev.clientY - r.top) / r.height - 0.5;
                card.style.transform =
                    `perspective(900px) rotateY(${px * 6}deg) rotateX(${-py * 6}deg) translateY(-4px)`;
            };
            this._onTiltLeave = (ev) => {
                const card = ev.target.closest(".o_binget_wh_card, .o_binget_kpi_card");
                if (card) card.style.transform = "";
            };
            this._tiltRoot.addEventListener("mousemove", this._onTiltMove);
            this._tiltRoot.addEventListener("mouseleave", this._onTiltLeave, true);
        });

        onWillUnmount(() => {
            if (this._tiltRoot && this._onTiltMove) {
                this._tiltRoot.removeEventListener("mousemove", this._onTiltMove);
                this._tiltRoot.removeEventListener("mouseleave", this._onTiltLeave, true);
            }
        });
    }

    async loadOverview() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("binget.stock.dashboard", "get_overview", []);
        } finally {
            this.state.loading = false;
        }
    }

    async openWarehouse(warehouseId, warehouseName) {
        this.state.view = "detail";
        this.state.currentWarehouseId = warehouseId;
        this.state.currentWarehouseName = warehouseName;
        this.state.search = "";
        this.state.categoryId = false;
        this.state.status = "all";
        this.state.page = 1;
        this.state.expandedId = null;
        this.state.units = null;
        this.state.animKey += 1;
        await this.loadDetail();
    }

    backToOverview() {
        this.state.view = "overview";
        this.state.detail = null;
        this.state.expandedId = null;
        this.state.units = null;
        this.state.animKey += 1;
        this.loadOverview();
    }

    async loadDetail() {
        this.state.detailLoading = true;
        this.state.expandedId = null;
        this.state.units = null;
        try {
            const offset = (this.state.page - 1) * this.state.pageSize;
            this.state.detail = await this.orm.call(
                "binget.stock.dashboard", "get_warehouse_products",
                [], {
                    warehouse_id: this.state.currentWarehouseId,
                    search: this.state.search,
                    category_id: this.state.categoryId,
                    status: this.state.status,
                    offset: offset,
                    limit: this.state.pageSize,
                }
            );
        } finally {
            this.state.detailLoading = false;
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.page = 1;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.loadDetail(), 280);
    }

    onCategoryChange(ev) {
        this.state.categoryId = ev.target.value ? parseInt(ev.target.value, 10) : false;
        this.state.page = 1;
        this.loadDetail();
    }

    setStatus(status) {
        this.state.status = status;
        this.state.page = 1;
        this.loadDetail();
    }

    nextPage() {
        if (this.state.page * this.state.pageSize < this.state.detail.total) {
            this.state.page++;
            this.loadDetail();
        }
    }

    prevPage() {
        if (this.state.page > 1) {
            this.state.page--;
            this.loadDetail();
        }
    }

    get pageCount() {
        if (!this.state.detail) return 1;
        return Math.max(1, Math.ceil(this.state.detail.total / this.state.pageSize));
    }

    // ---------------------------------------------------------------
    // Serial / lot expand
    // ---------------------------------------------------------------
    async toggleUnits(productId, isTracked) {
        if (!isTracked) {
            // quantity-tracked → open product form directly
            this.openProduct(productId);
            return;
        }
        if (this.state.expandedId === productId) {
            this.state.expandedId = null;
            this.state.units = null;
            return;
        }
        this.state.expandedId = productId;
        this.state.unitsLoading = true;
        this.state.units = null;
        try {
            this.state.units = await this.orm.call(
                "binget.stock.dashboard", "get_product_units",
                [], {
                    product_id: productId,
                    warehouse_id: this.state.currentWarehouseId,
                }
            );
        } finally {
            this.state.unitsLoading = false;
        }
    }

    openNewWarehouse() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "stock.warehouse",
            views: [[false, "form"]],
            target: "new",
            name: "New Warehouse",
        });
    }

    openProduct(productId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.product",
            res_id: productId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openHistory(productId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Move History",
            res_model: "stock.move.line",
            views: [[false, "list"], [false, "form"]],
            domain: [["product_id", "=", productId], ["state", "=", "done"]],
            target: "current",
        });
    }

    openLotHistory(lotId, productId) {
        const domain = [["product_id", "=", productId], ["state", "=", "done"]];
        if (lotId) {
            domain.push(["lot_id", "=", lotId]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Move History",
            res_model: "stock.move.line",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
            target: "current",
        });
    }

    // ---------------------------------------------------------------
    // Formatting / health segments (full-width like Command Center)
    // ---------------------------------------------------------------
    fmtNumber(value) {
        return this.compactNumber(value || 0);
    }

    fmtMoney(value) {
        const symbol = (this.state.data && this.state.data.currency_symbol) ||
            (this.state.detail && this.state.detail.currency_symbol) || "";
        return `${this.compactNumber(value || 0)} ${symbol}`.trim();
    }

    compactNumber(value) {
        const n = Number(value) || 0;
        const abs = Math.abs(n);
        const sign = n < 0 ? "-" : "";
        if (abs >= 1e9) {
            return sign + (abs / 1e9).toFixed(abs >= 1e10 ? 0 : 1).replace(/\.0$/, "") + "B";
        }
        if (abs >= 1e6) {
            return sign + (abs / 1e6).toFixed(abs >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
        }
        if (abs >= 1e4) {
            return sign + (abs / 1e3).toFixed(abs >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "K";
        }
        if (abs >= 100) {
            return sign + Math.round(abs).toLocaleString();
        }
        if (Math.abs(n - Math.round(n)) > 0.001) {
            return sign + abs.toFixed(2);
        }
        return sign + String(Math.round(abs));
    }

    statusLabel(status) {
        return {
            good_stock: "Good Stock",
            low_stock: "Low Stock",
            out_of_stock: "Out of Stock",
        }[status] || status;
    }

    /** Segment widths for the full health bar (percentages that sum to 100). */
    healthSegments(wh) {
        const total = Math.max(
            (wh.good_stock || 0) + (wh.low_stock || 0),
            wh.products || 1,
            1
        );
        // low_stock already includes out_of_stock in our backend counts
        const out = wh.out_of_stock || 0;
        const lowOnly = Math.max(0, (wh.low_stock || 0) - out);
        const good = Math.max(0, total - (wh.low_stock || 0));
        const sum = good + lowOnly + out || 1;
        return {
            good: (good / sum) * 100,
            low: (lowOnly / sum) * 100,
            out: (out / sum) * 100,
        };
    }
}

BingetStockDashboard.template = "binget_stock_dashboard.Dashboard";

registry.category("actions").add("binget_stock_dashboard", BingetStockDashboard);

export default BingetStockDashboard;
