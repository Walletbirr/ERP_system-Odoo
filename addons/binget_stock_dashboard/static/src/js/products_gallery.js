/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";

const { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } = owl;

class BingetProductsGallery extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");

        this.state = useState({
            loading: true,
            rows: [],
            total: 0,
            counts: { all: 0, in_stock: 0, low_stock: 0, out_of_stock: 0 },
            totalOnHand: 0,
            totalValue: 0,
            categories: [],
            search: "",
            categoryId: false,
            status: "all",
            favoriteOnly: false,
            page: 1,
            pageSize: 24,
            currency_symbol: "",
            animKey: 0,
        });

        onWillStart(async () => {
            this.state.categories = await this.orm.call(
                "binget.stock.dashboard", "get_categories", []
            );
            await this.load();
        });

        onMounted(() => {
            this._tiltRoot = this.rootRef.el;
            if (!this._tiltRoot) return;
            this._onTiltMove = (ev) => {
                const card = ev.target.closest(".o_bp_card");
                if (!card || !this._tiltRoot.contains(card)) return;
                const r = card.getBoundingClientRect();
                const px = (ev.clientX - r.left) / r.width - 0.5;
                const py = (ev.clientY - r.top) / r.height - 0.5;
                card.style.transform =
                    `perspective(900px) rotateY(${px * 7}deg) rotateX(${-py * 7}deg) translateY(-4px) scale(1.01)`;
            };
            this._onTiltLeave = (ev) => {
                const card = ev.target.closest(".o_bp_card");
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

    async load() {
        this.state.loading = true;
        try {
            const offset = (this.state.page - 1) * this.state.pageSize;
            const data = await this.orm.call(
                "binget.stock.dashboard", "get_products_gallery",
                [], {
                    search: this.state.search,
                    category_id: this.state.categoryId,
                    status: this.state.status,
                    favorite_only: this.state.favoriteOnly,
                    offset: offset,
                    limit: this.state.pageSize,
                }
            );
            this.state.rows = data.rows;
            this.state.total = data.total;
            this.state.counts = data.counts || this.state.counts;
            this.state.totalOnHand = data.total_on_hand || 0;
            this.state.totalValue = data.total_value || 0;
            this.state.currency_symbol = data.currency_symbol || "";
            this.state.animKey += 1;
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.page = 1;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.load(), 280);
    }

    onCategoryChange(ev) {
        this.state.categoryId = ev.target.value ? parseInt(ev.target.value, 10) : false;
        this.state.page = 1;
        this.load();
    }

    getTabClass(status) {
        return {
            active: this.state.status === status && !this.state.favoriteOnly,
        };
    }

    getFavoriteTabClass() {
        return {
            active: !!this.state.favoriteOnly,
        };
    }

    setStatus(status) {
        this.state.status = status;
        this.state.favoriteOnly = false;
        this.state.page = 1;
        this.load();
    }

    toggleFavoriteFilter() {
        // Exclusive: Favorites tab on → clear status filters; off → back to All
        if (this.state.favoriteOnly) {
            this.state.favoriteOnly = false;
            this.state.status = "all";
        } else {
            this.state.favoriteOnly = true;
            this.state.status = "all";
        }
        this.state.page = 1;
        this.load();
    }

    async onFavoriteClick(ev, product) {
        ev.stopPropagation();
        ev.preventDefault();
        const tmplId = product.tmpl_id;
        if (!tmplId) return;
        try {
            const next = await this.orm.call(
                "binget.stock.dashboard",
                "toggle_product_favorite",
                [tmplId]
            );
            product.is_favorite = !!next;
            // If viewing favorites only and unfavorited, reload list
            if (this.state.favoriteOnly) {
                await this.load();
            }
        } catch (e) {
            console.error("toggle favorite failed", e);
        }
    }

    nextPage() {
        if (this.state.page * this.state.pageSize < this.state.total) {
            this.state.page++;
            this.load();
        }
    }

    prevPage() {
        if (this.state.page > 1) {
            this.state.page--;
            this.load();
        }
    }

    get pageCount() {
        return Math.max(1, Math.ceil(this.state.total / this.state.pageSize));
    }

    openProduct(productId) {
        // Standard Odoo product form (full default view)
        const row = this.state.rows.find((r) => r.id === productId);
        const tmplId = row && row.tmpl_id;
        if (!tmplId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: tmplId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openNewProduct() {
        // The gallery only lists is_storable (="Track Inventory") products.
        // The standard form leaves that checkbox unticked by default, so a
        // product created here would silently vanish from this list even
        // though it saved fine (visible in Sales/Inventory). Default it on,
        // since anything created from a stock dashboard should be tracked.
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "product.template",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_is_storable: true,
                },
            },
            {
                onClose: () => this.load(),
            }
        );
    }

    fmtNumber(value) {
        return this.compactNumber(value || 0);
    }

    fmtMoney(value) {
        const sym = this.state.currency_symbol || "";
        const compact = this.compactNumber(value || 0);
        return `${compact} ${sym}`.trim();
    }

    /** 1234 → 1.2K · 2_500_000 → 2.5M · small values stay precise */
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
        // prices / small qty — keep 2 decimals if fractional
        if (Math.abs(n - Math.round(n)) > 0.001) {
            return sign + abs.toFixed(2);
        }
        return sign + String(Math.round(abs));
    }

    statusLabel(status) {
        return {
            good_stock: "In Stock",
            low_stock: "Low Stock",
            out_of_stock: "Out of Stock",
        }[status] || status;
    }
}

BingetProductsGallery.template = "binget_stock_dashboard.ProductsGallery";
registry.category("actions").add("binget_products_gallery", BingetProductsGallery);
export default BingetProductsGallery;
