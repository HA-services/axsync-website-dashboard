/** @odoo-module **/
// Dashboard engine: loads a dashboard and renders its grid of items. Framework independent, used by the
// website pages, the website embeds and the back-end client action.

import * as l10n from "@web/core/l10n/translation";

import { CHART_TYPES, drawChart, drawGauge } from "./charts";
import { contrastColor, downloadBlob, escapeHtml, formatNumber, formatPercent, PALETTES, shade, slugify } from "./format";
import { icon } from "./icons";

/** Translate a term; English is used while the translations are not loaded yet (public website pages). */
function _t(term) {
    const loaded = l10n.translationLoaded ? l10n.translatedTerms[l10n.translationLoaded] : true;
    if (!loaded) {
        return term;
    }
    try {
        return String(l10n._t(term));
    } catch {
        return term;
    }
}

const ROW_HEIGHT = 72;
const GAP = 16;
const COLS = 12;
const NARROW = 768;

/**
 * Never called: lists the terms used inside template literals so that Odoo's translation export finds them.
 */
// eslint-disable-next-line no-unused-vars
function translatableTerms() {
    return [
        _t("This dashboard cannot be displayed."),
        _t("This dashboard has no items yet."),
        _t("Add an item"),
        _t("Period"),
        _t("From"),
        _t("To"),
        _t("Apply"),
        _t("Refresh"),
        _t("Full screen"),
        _t("Edit layout"),
        _t("Done"),
        _t("Edit Layout"),
        _t("Add item"),
        _t("Add Item"),
        _t("Settings"),
        _t("Open on the website"),
        _t("Back"),
        _t("Download CSV"),
        _t("Download image"),
        _t("Open records"),
        _t("Edit item"),
        _t("vs %(value)s previous period"),
        _t("Previous period: %(value)s"),
        _t("%(pct)s of %(target)s"),
        _t("No data for this period"),
        _t("No records"),
        _t("%(first)s-%(last)s of %(total)s"),
        _t("Previous"),
        _t("Next"),
        _t("No tasks"),
        _t("Drag to move"),
        _t("Drag to resize"),
        _t("Target"),
    ];
}

export async function jsonRpc(url, params) {
    const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: Date.now(), params }),
    });
    const data = await response.json();
    if (data.error) {
        const message = (data.error.data && data.error.data.message) || data.error.message || "Error";
        throw new Error(message);
    }
    return data.result;
}

function fill(text, values) {
    return String(text).replace(/%\((\w+)\)s/g, (_m, key) => (key in values ? values[key] : ""));
}

export class DashboardEngine {
    /**
     * @param {HTMLElement} el container
     * @param {Object} options
     *   dashboardId, channel ("website" | "backend"), rpc(url, params),
     *   onOpenRecords({model, domain, name, resId}), onEditItem(id), onAddItem(layout),
     *   onOpenSettings(), notify(message, type), compactHeader (embeds)
     */
    constructor(el, options) {
        this.el = el;
        this.options = Object.assign({ channel: "website", rpc: jsonRpc }, options);
        this.state = { dateFilter: null, dateFrom: null, dateTo: null, drill: {}, pages: {}, hidden: {}, editing: false };
        this.data = null;
        this.timer = null;
        this.loading = false;
        this.observers = [];
        this.destroyed = false;
        this.el.classList.add("o_axs_dashboard");
        this._onVisibility = () => this._setupRefresh();
        document.addEventListener("visibilitychange", this._onVisibility);
        this._resizeObserver = new ResizeObserver(() => this._onResize());
        this._resizeObserver.observe(this.el);
    }

    get isBackend() {
        return this.options.channel === "backend";
    }

    get locale() {
        return (this.data && this.data.lang) || document.documentElement.lang || "en-US";
    }

    get palette() {
        return PALETTES[(this.data && this.data.theme) || "axsync"] || PALETTES.axsync;
    }

    async start() {
        this.el.innerHTML = `<div class="o_axs_loading">${this._skeleton()}</div>`;
        await this.load();
    }

    destroy() {
        this.destroyed = true;
        clearInterval(this.timer);
        document.removeEventListener("visibilitychange", this._onVisibility);
        this._resizeObserver.disconnect();
        this._hideTooltip();
        if (this.tooltipEl) {
            this.tooltipEl.remove();
        }
    }

    _skeleton() {
        return `<div class="o_axs_skeleton">${'<div class="o_axs_skel_card"></div>'.repeat(6)}</div>`;
    }

    _params(itemIds) {
        return {
            dashboard_id: this.options.dashboardId,
            channel: this.options.channel,
            date_filter: this.state.dateFilter,
            date_from: this.state.dateFrom,
            date_to: this.state.dateTo,
            drill: this.state.drill,
            pages: this.state.pages,
            item_ids: itemIds || null,
        };
    }

    async load(itemIds = null, { silent = false } = {}) {
        if (this.destroyed) {
            return;
        }
        this.loading = true;
        if (!silent && this.headerEl) {
            this.headerEl.classList.add("o_axs_busy");
        }
        let result;
        try {
            result = await this.options.rpc("/axs_dashboard/data", this._params(itemIds));
        } catch (error) {
            this.loading = false;
            this._renderError(error.message || String(error));
            return;
        }
        this.loading = false;
        if (this.destroyed) {
            return;
        }
        if (this.headerEl) {
            this.headerEl.classList.remove("o_axs_busy");
        }
        if (!result || result.error) {
            this._renderError((result && result.error) || _t("This dashboard cannot be displayed."));
            return;
        }
        if (itemIds && this.data) {
            const byId = Object.fromEntries(result.items.map((i) => [i.id, i]));
            this.data.items = this.data.items.map((i) => byId[i.id] || i);
            for (const id of itemIds) {
                if (byId[id]) {
                    this._renderItem(byId[id]);
                }
            }
        } else {
            this.data = result;
            this.state.dateFilter = result.date_filter;
            this.render();
        }
        this._setupRefresh();
    }

    _renderError(message) {
        this.el.innerHTML = `<div class="o_axs_message">${icon("lock", 28)}<div>${escapeHtml(message)}</div></div>`;
    }

    _setupRefresh() {
        clearInterval(this.timer);
        const interval = this.data && this.data.refresh_interval;
        if (interval && !document.hidden && !this.state.editing) {
            this.timer = setInterval(() => {
                if (!this.loading && !document.hidden) {
                    this.load(null, { silent: true });
                }
            }, interval * 1000);
        }
    }

    // ------------------------------------------------------------------ rendering
    render() {
        const d = this.data;
        this.el.innerHTML = "";
        this.el.className = `o_axs_dashboard o_axs_theme_${d.theme} ${this.state.editing ? "o_axs_editing" : ""}`;
        this.el.appendChild(this._renderHeader());
        if (!d.items.length) {
            const empty = document.createElement("div");
            empty.className = "o_axs_message";
            empty.innerHTML = `${icon("chart", 32)}<div>${escapeHtml(_t("This dashboard has no items yet."))}</div>`;
            if (d.can_edit) {
                const btn = document.createElement("button");
                btn.className = "btn btn-primary mt-3";
                btn.textContent = _t("Add an item");
                btn.addEventListener("click", () => this.options.onAddItem && this.options.onAddItem(this._nextSlot(6, 4)));
                empty.appendChild(btn);
            }
            this.el.appendChild(empty);
            return;
        }
        this.gridEl = document.createElement("div");
        this.gridEl.className = "o_axs_grid";
        this.gridEl.style.setProperty("--axs-row", `${ROW_HEIGHT}px`);
        this.gridEl.style.setProperty("--axs-gap", `${GAP}px`);
        this.el.appendChild(this.gridEl);
        this.itemEls = {};
        for (const item of d.items) {
            this._renderItem(item);
        }
        this._onResize();
    }

    _renderHeader() {
        const d = this.data;
        const header = document.createElement("div");
        header.className = "o_axs_header";
        const compact = this.options.compactHeader;
        let filter = "";
        if (d.show_date_filter) {
            const options = d.date_filters
                .map((f) => `<option value="${f.key}" ${f.key === this.state.dateFilter ? "selected" : ""}>${escapeHtml(f.label)}</option>`)
                .join("");
            const custom = this.state.dateFilter === "custom";
            filter = `<div class="o_axs_filter">
                <select class="form-select form-select-sm o_axs_date_filter" aria-label="${escapeHtml(_t("Period"))}">${options}</select>
                <span class="o_axs_custom ${custom ? "" : "d-none"}">
                    <input type="date" class="form-control form-control-sm o_axs_from" value="${escapeHtml(this.state.dateFrom || "")}" aria-label="${escapeHtml(_t("From"))}"/>
                    <input type="date" class="form-control form-control-sm o_axs_to" value="${escapeHtml(this.state.dateTo || "")}" aria-label="${escapeHtml(_t("To"))}"/>
                    <button type="button" class="btn btn-sm btn-primary o_axs_apply">${escapeHtml(_t("Apply"))}</button>
                </span>
            </div>`;
        }
        const buttons = [];
        buttons.push(`<button type="button" class="btn btn-sm btn-light o_axs_btn_refresh" title="${escapeHtml(_t("Refresh"))}">${icon("refresh", 16)}</button>`);
        buttons.push(`<button type="button" class="btn btn-sm btn-light o_axs_btn_fullscreen" title="${escapeHtml(_t("Full screen"))}">${icon("expand", 16)}</button>`);
        if (d.can_edit) {
            buttons.push(`<button type="button" class="btn btn-sm ${this.state.editing ? "btn-primary" : "btn-light"} o_axs_btn_edit" title="${escapeHtml(_t("Edit layout"))}">${icon("move", 16)}<span>${escapeHtml(this.state.editing ? _t("Done") : _t("Edit Layout"))}</span></button>`);
            buttons.push(`<button type="button" class="btn btn-sm btn-light o_axs_btn_add" title="${escapeHtml(_t("Add item"))}">${icon("plus", 16)}<span>${escapeHtml(_t("Add Item"))}</span></button>`);
            buttons.push(`<button type="button" class="btn btn-sm btn-light o_axs_btn_settings" title="${escapeHtml(_t("Settings"))}">${icon("gear", 16)}</button>`);
        }
        if (this.isBackend && d.website_url) {
            buttons.push(`<a class="btn btn-sm btn-light" href="${escapeHtml(d.website_url)}" target="_blank" rel="noopener" title="${escapeHtml(_t("Open on the website"))}">${icon("external", 16)}</a>`);
        }
        header.innerHTML = `
            <div class="o_axs_title_block">
                ${compact ? `<div class="o_axs_title h5 mb-0">${escapeHtml(d.name)}</div>` : `<h2 class="o_axs_title">${escapeHtml(d.name)}</h2>`}
                ${d.description && !compact ? `<div class="o_axs_subtitle">${escapeHtml(d.description)}</div>` : ""}
            </div>
            <div class="o_axs_toolbar">${filter}<div class="o_axs_buttons">${buttons.join("")}</div><span class="o_axs_spinner" aria-hidden="true"></span></div>`;
        const select = header.querySelector(".o_axs_date_filter");
        if (select) {
            select.addEventListener("change", () => {
                this.state.dateFilter = select.value;
                if (select.value === "custom") {
                    header.querySelector(".o_axs_custom").classList.remove("d-none");
                    return;
                }
                this.state.dateFrom = this.state.dateTo = null;
                this.state.drill = {};
                this.state.pages = {};
                this.load();
            });
            header.querySelector(".o_axs_apply").addEventListener("click", () => {
                this.state.dateFrom = header.querySelector(".o_axs_from").value || null;
                this.state.dateTo = header.querySelector(".o_axs_to").value || null;
                this.state.drill = {};
                this.state.pages = {};
                this.load();
            });
        }
        header.querySelector(".o_axs_btn_refresh").addEventListener("click", () => this.load());
        header.querySelector(".o_axs_btn_fullscreen").addEventListener("click", () => this.toggleFullscreen());
        if (d.can_edit) {
            header.querySelector(".o_axs_btn_edit").addEventListener("click", () => this.toggleEdit());
            header.querySelector(".o_axs_btn_add").addEventListener("click", () => this.options.onAddItem && this.options.onAddItem(this._nextSlot(4, 3)));
            header.querySelector(".o_axs_btn_settings").addEventListener("click", () => this.options.onOpenSettings && this.options.onOpenSettings());
        }
        this.headerEl = header;
        return header;
    }

    toggleFullscreen() {
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else if (this.el.requestFullscreen) {
            this.el.requestFullscreen().catch(() => {});
        }
    }

    toggleEdit() {
        this.state.editing = !this.state.editing;
        this.render();
        this._setupRefresh();
    }

    _nextSlot(w, h) {
        const bottom = Math.max(0, ...this.data.items.map((i) => i.y + i.h));
        return { x: 0, y: bottom, w, h };
    }

    _placeEl(el, item) {
        el.style.gridColumn = `${item.x + 1} / span ${Math.min(item.w, COLS - item.x)}`;
        el.style.gridRow = `${item.y + 1} / span ${item.h}`;
        el.style.setProperty("--axs-h", item.h);
        el.style.order = String(item.y * COLS + item.x);
    }

    _renderItem(item) {
        let el = this.itemEls[item.id];
        const fresh = !el;
        if (fresh) {
            el = document.createElement("div");
            el.className = "o_axs_item";
            el.dataset.itemId = item.id;
            this.itemEls[item.id] = el;
            this.gridEl.appendChild(el);
        }
        el.className = `o_axs_item o_axs_item_${item.type}`;
        this._placeEl(el, item);
        const data = item.data || {};
        el.innerHTML = "";
        if (item.type === "tile" || item.type === "kpi") {
            this._renderTile(el, item, data);
        } else {
            this._renderCard(el, item, data);
        }
        if (this.state.editing) {
            this._addEditHandles(el, item);
        }
    }

    _actionsHtml(item, data) {
        const acts = [];
        const chart = CHART_TYPES.includes(item.type) || item.type === "gauge";
        if (data.drill && data.drill.length) {
            acts.push(`<button type="button" class="o_axs_act o_axs_act_back" title="${escapeHtml(_t("Back"))}">${icon("back", 15)}</button>`);
        }
        if (!data.error && (chart || item.type === "list")) {
            acts.push(`<button type="button" class="o_axs_act o_axs_act_csv" title="${escapeHtml(_t("Download CSV"))}">${icon("download", 15)}</button>`);
        }
        if (!data.error && chart) {
            acts.push(`<button type="button" class="o_axs_act o_axs_act_png" title="${escapeHtml(_t("Download image"))}">${icon("image", 15)}</button>`);
        }
        if (this.isBackend && item.open_records && data.domain && item.model_name) {
            acts.push(`<button type="button" class="o_axs_act o_axs_act_records" title="${escapeHtml(_t("Open records"))}">${icon("list", 15)}</button>`);
        }
        if (this.data.can_edit && this.options.onEditItem) {
            acts.push(`<button type="button" class="o_axs_act o_axs_act_edit" title="${escapeHtml(_t("Edit item"))}">${icon("edit", 15)}</button>`);
        }
        return acts.join("");
    }

    _bindActions(el, item, data) {
        const on = (sel, fn) => {
            const b = el.querySelector(sel);
            if (b) {
                b.addEventListener("click", (ev) => {
                    ev.stopPropagation();
                    fn();
                });
            }
        };
        on(".o_axs_act_back", () => {
            delete this.state.drill[item.id];
            this.load([item.id]);
        });
        on(".o_axs_act_csv", () => this.exportCsv(item));
        on(".o_axs_act_png", () => this.exportPng(item, el));
        on(".o_axs_act_records", () => this._openRecords(item, data.domain));
        on(".o_axs_act_edit", () => this.options.onEditItem(item.id));
    }

    _openRecords(item, domain, resId) {
        if (this.options.onOpenRecords && item.model_name) {
            this.options.onOpenRecords({ model: item.model_name, domain: domain || [], name: item.name, resId });
        }
    }

    _renderTile(el, item, data) {
        const color = item.color || this.palette[0];
        const style = item.style || "light";
        el.classList.add(`o_axs_tile_${style}`);
        el.style.setProperty("--axs-color", color);
        el.style.setProperty("--axs-color-soft", shade(color, 0.88));
        el.style.setProperty("--axs-color-text", style === "solid" ? contrastColor(color) : "");
        const clickable = (this.isBackend && item.open_records && data.domain) || (!this.isBackend && item.link_url);
        let compare = "";
        if (!data.error && item.type === "kpi") {
            if (item.comparison === "previous" && data.change !== undefined && data.change !== null) {
                const up = data.change >= 0;
                compare = `<div class="o_axs_compare ${up ? "o_axs_up" : "o_axs_down"}">${icon(up ? "up" : "down", 14)}<b>${escapeHtml(formatPercent(Math.abs(data.change), this.locale))}</b><span>${escapeHtml(fill(_t("vs %(value)s previous period"), { value: formatNumber(data.previous, item.format, this.locale, { short: true }) }))}</span></div>`;
            } else if (item.comparison === "previous" && data.previous !== undefined) {
                compare = `<div class="o_axs_compare">${escapeHtml(fill(_t("Previous period: %(value)s"), { value: formatNumber(data.previous, item.format, this.locale, { short: true }) }))}</div>`;
            } else if (item.comparison === "target" && data.target) {
                const pct = Math.max(0, Math.min(100, data.progress || 0));
                compare = `<div class="o_axs_progress"><div class="o_axs_progress_bar" style="width:${pct}%"></div></div><div class="o_axs_compare">${escapeHtml(fill(_t("%(pct)s of %(target)s"), { pct: formatPercent(data.progress || 0, this.locale, 0), target: formatNumber(data.target, item.format, this.locale, { short: true }) }))}</div>`;
            }
        }
        const value = data.error ? "" : formatNumber(data.value, item.format, this.locale);
        el.innerHTML = `
            <div class="o_axs_tile_inner ${clickable ? "o_axs_clickable" : ""}" ${clickable ? 'tabindex="0" role="button"' : ""}>
                <div class="o_axs_tile_icon">${icon(item.icon, 26)}</div>
                <div class="o_axs_tile_body">
                    <div class="o_axs_tile_name" title="${escapeHtml(item.description || item.name)}">${escapeHtml(item.name)}</div>
                    ${data.error ? `<div class="o_axs_tile_error">${escapeHtml(data.error)}</div>` : `<div class="o_axs_tile_value" title="${escapeHtml(value)}">${escapeHtml(value)}</div>`}
                    ${compare}
                </div>
                <div class="o_axs_item_actions">${this._actionsHtml(item, data)}</div>
            </div>`;
        this._bindActions(el, item, data);
        if (clickable) {
            const inner = el.querySelector(".o_axs_tile_inner");
            const go = () => {
                if (this.state.editing) {
                    return;
                }
                if (this.isBackend) {
                    this._openRecords(item, data.domain);
                } else {
                    window.location.href = item.link_url;
                }
            };
            inner.addEventListener("click", go);
            inner.addEventListener("keydown", (ev) => ev.key === "Enter" && go());
        }
    }

    _renderCard(el, item, data) {
        const breadcrumb = data.drill && data.drill.length ? `<span class="o_axs_crumb">› ${escapeHtml(data.drill[0].label)}</span>` : "";
        el.innerHTML = `
            <div class="o_axs_card">
                <header class="o_axs_card_head">
                    <div class="o_axs_card_title">
                        <div class="o_axs_card_name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}${breadcrumb}</div>
                        ${item.description ? `<div class="o_axs_card_desc">${escapeHtml(item.description)}</div>` : ""}
                    </div>
                    <div class="o_axs_item_actions">${this._actionsHtml(item, data)}</div>
                </header>
                <div class="o_axs_card_body"></div>
            </div>`;
        this._bindActions(el, item, data);
        const body = el.querySelector(".o_axs_card_body");
        if (data.error) {
            body.innerHTML = `<div class="o_axs_message o_axs_small">${icon(data.no_access ? "lock" : "empty", 24)}<div>${escapeHtml(data.error)}</div></div>`;
            return;
        }
        if (CHART_TYPES.includes(item.type)) {
            this._drawChart(body, item, data);
        } else if (item.type === "gauge") {
            body.classList.add("o_axs_gauge_body");
            requestAnimationFrame(() => drawGauge(body, item, data, this._chartCtx(item, data)));
        } else if (item.type === "list") {
            this._renderList(body, item, data);
        } else if (item.type === "todo") {
            this._renderTodo(body, item, data);
        } else if (item.type === "text") {
            body.classList.add("o_axs_text");
            body.innerHTML = data.html || "";
        }
    }

    _isEmpty(data) {
        return !data.labels || !data.labels.length || data.datasets.every((d) => d.values.every((v) => !v));
    }

    _chartCtx(item, data) {
        const hidden = (this.state.hidden[item.id] = this.state.hidden[item.id] || new Set());
        return {
            palette: this.palette,
            locale: this.locale,
            hidden,
            tooltip: { show: (html, ev) => this._showTooltip(html, ev), hide: () => this._hideTooltip() },
            onToggle: (i) => {
                if (hidden.has(i)) {
                    hidden.delete(i);
                } else {
                    hidden.add(i);
                }
                this._renderItem(item);
            },
            onSegment: (i) => this._onSegment(item, data, i),
        };
    }

    _drawChart(body, item, data) {
        body.classList.add("o_axs_chart");
        if (this._isEmpty(data)) {
            body.innerHTML = `<div class="o_axs_message o_axs_small">${icon("empty", 24)}<div>${escapeHtml(_t("No data for this period"))}</div></div>`;
            return;
        }
        // wait for the layout so that the chart gets the final size of its box
        requestAnimationFrame(() => {
            if (!body.isConnected) {
                return;
            }
            drawChart(body, item, data, this._chartCtx(item, data));
            body.dataset.size = `${body.clientWidth}x${body.clientHeight}`;
        });
    }

    _onSegment(item, data, index) {
        if (this.state.editing) {
            return;
        }
        const key = data.keys ? data.keys[index] : undefined;
        if (data.can_drill && key !== undefined && key !== null) {
            this.state.drill[item.id] = [key];
            this.state.hidden[item.id] = new Set();
            this.load([item.id]);
        } else if (this.isBackend && item.open_records && data.group_domains && data.group_domains[index]) {
            this._openRecords(item, data.group_domains[index]);
        }
    }

    _renderList(body, item, data) {
        body.classList.add("o_axs_list");
        const fmt = (v) => formatNumber(v, item.format, this.locale);
        if (data.grouped) {
            const max = Math.max(...data.rows.map((r) => Math.abs(r.value)), 0) || 1;
            body.innerHTML = data.rows.length
                ? `<table class="table table-sm o_axs_table"><thead><tr><th>${escapeHtml(data.columns[0])}</th><th class="text-end">${escapeHtml(data.columns[1])}</th></tr></thead><tbody>${data.rows
                      .map(
                          (r) => `<tr><td><div class="o_axs_bar_cell"><span class="o_axs_bar_fill" style="width:${(Math.abs(r.value) / max) * 100}%;background:${item.color}"></span><span>${escapeHtml(r.label)}</span></div></td><td class="text-end">${escapeHtml(fmt(r.value))}</td></tr>`
                      )
                      .join("")}</tbody></table>`
                : `<div class="o_axs_message o_axs_small">${icon("empty", 24)}<div>${escapeHtml(_t("No data for this period"))}</div></div>`;
            return;
        }
        if (!data.rows.length) {
            body.innerHTML = `<div class="o_axs_message o_axs_small">${icon("empty", 24)}<div>${escapeHtml(_t("No records"))}</div></div>`;
            return;
        }
        const numeric = (type) => ["integer", "float", "monetary"].includes(type);
        const cell = (v, col) => {
            if (col.type === "boolean") {
                return v ? "✓" : "";
            }
            if (numeric(col.type) && v !== "" && v !== null) {
                return escapeHtml(formatNumber(v, col.type === "integer" ? { ...item.format, decimals: 0, currency: false } : item.format, this.locale));
            }
            return escapeHtml(v);
        };
        const pages = Math.max(1, Math.ceil(data.total / data.page_size));
        const first = data.page * data.page_size + 1;
        const last = Math.min(data.total, first + data.rows.length - 1);
        body.innerHTML = `
            <div class="o_axs_table_wrap"><table class="table table-sm table-hover o_axs_table">
                <thead><tr>${data.columns.map((c) => `<th class="${numeric(c.type) ? "text-end" : ""}">${escapeHtml(c.label)}</th>`).join("")}</tr></thead>
                <tbody>${data.rows
                    .map((r) => `<tr data-id="${r.id}" class="${this.isBackend && item.open_records ? "o_axs_clickable" : ""}">${r.cells.map((v, i) => `<td class="${numeric(data.columns[i].type) ? "text-end" : ""}">${cell(v, data.columns[i])}</td>`).join("")}</tr>`)
                    .join("")}</tbody>
            </table></div>
            <div class="o_axs_pager">
                <span>${escapeHtml(fill(_t("%(first)s-%(last)s of %(total)s"), { first, last, total: data.total }))}</span>
                <button type="button" class="btn btn-sm btn-light o_axs_prev" ${data.page <= 0 ? "disabled" : ""} aria-label="${escapeHtml(_t("Previous"))}">‹</button>
                <button type="button" class="btn btn-sm btn-light o_axs_next" ${data.page >= pages - 1 ? "disabled" : ""} aria-label="${escapeHtml(_t("Next"))}">›</button>
            </div>`;
        const page = (delta) => {
            this.state.pages[item.id] = Math.max(0, (data.page || 0) + delta);
            this.load([item.id]);
        };
        body.querySelector(".o_axs_prev").addEventListener("click", () => page(-1));
        body.querySelector(".o_axs_next").addEventListener("click", () => page(1));
        if (this.isBackend && item.open_records) {
            body.querySelectorAll("tbody tr").forEach((tr) => {
                tr.addEventListener("click", () => this._openRecords(item, [["id", "=", Number(tr.dataset.id)]], Number(tr.dataset.id)));
            });
        }
    }

    _renderTodo(body, item, data) {
        body.classList.add("o_axs_todo");
        const todos = data.todos || [];
        const editable = this.data.can_edit;
        const done = todos.filter((t) => t.done).length;
        body.innerHTML = todos.length
            ? `<div class="o_axs_todo_progress"><div class="o_axs_progress"><div class="o_axs_progress_bar" style="width:${(done / todos.length) * 100}%"></div></div><span>${done}/${todos.length}</span></div>
               <ul class="list-unstyled mb-0">${todos
                   .map((t) => `<li><label class="${t.done ? "o_axs_done" : ""}"><input type="checkbox" data-todo="${t.id}" ${t.done ? "checked" : ""} ${editable ? "" : "disabled"}/> <span>${escapeHtml(t.name)}</span></label></li>`)
                   .join("")}</ul>`
            : `<div class="o_axs_message o_axs_small">${icon("check", 24)}<div>${escapeHtml(_t("No tasks"))}</div></div>`;
        if (editable) {
            body.querySelectorAll("input[data-todo]").forEach((input) => {
                input.addEventListener("change", async () => {
                    try {
                        await this.options.rpc("/axs_dashboard/todo", { todo_id: Number(input.dataset.todo), done: input.checked });
                        this.load([item.id], { silent: true });
                    } catch (error) {
                        input.checked = !input.checked;
                        this._notify(error.message, "danger");
                    }
                });
            });
        }
    }

    // ------------------------------------------------------------------ tooltip
    _showTooltip(html, ev) {
        if (!this.tooltipEl) {
            this.tooltipEl = document.createElement("div");
            this.tooltipEl.className = "o_axs_tooltip";
            document.body.appendChild(this.tooltipEl);
        }
        this.tooltipEl.innerHTML = html;
        this.tooltipEl.style.display = "block";
        const pad = 14;
        const rect = this.tooltipEl.getBoundingClientRect();
        let x = ev.clientX + pad;
        let y = ev.clientY + pad;
        if (x + rect.width > window.innerWidth - 8) {
            x = ev.clientX - rect.width - pad;
        }
        if (y + rect.height > window.innerHeight - 8) {
            y = ev.clientY - rect.height - pad;
        }
        this.tooltipEl.style.transform = `translate(${Math.max(4, x)}px, ${Math.max(4, y)}px)`;
    }

    _hideTooltip() {
        if (this.tooltipEl) {
            this.tooltipEl.style.display = "none";
        }
    }

    _notify(message, type = "info") {
        if (this.options.notify) {
            this.options.notify(message, type);
        } else {
            console.warn(message);
        }
    }

    // ------------------------------------------------------------------ responsive
    _onResize() {
        if (!this.gridEl) {
            return;
        }
        const narrow = this.el.clientWidth < NARROW;
        this.el.classList.toggle("o_axs_narrow", narrow);
        clearTimeout(this._resizeTimer);
        this._resizeTimer = setTimeout(() => {
            for (const item of this.data.items) {
                const el = this.itemEls[item.id];
                const body = el && el.querySelector(".o_axs_chart, .o_axs_gauge_body");
                if (body && body.dataset.size !== `${body.clientWidth}x${body.clientHeight}`) {
                    this._renderItem(item);
                }
            }
        }, 120);
    }

    // ------------------------------------------------------------------ layout editing
    _cellSize() {
        const width = this.gridEl.clientWidth;
        return { col: (width - GAP * (COLS - 1)) / COLS, row: ROW_HEIGHT };
    }

    _addEditHandles(el, item) {
        const move = document.createElement("div");
        move.className = "o_axs_move_handle";
        move.title = _t("Drag to move");
        move.innerHTML = icon("move", 16);
        const resize = document.createElement("div");
        resize.className = "o_axs_resize_handle";
        resize.title = _t("Drag to resize");
        el.appendChild(move);
        el.appendChild(resize);
        move.addEventListener("pointerdown", (ev) => this._startDrag(ev, el, item, "move"));
        resize.addEventListener("pointerdown", (ev) => this._startDrag(ev, el, item, "resize"));
    }

    _startDrag(ev, el, item, mode) {
        ev.preventDefault();
        const handle = ev.currentTarget;
        handle.setPointerCapture(ev.pointerId);
        const start = { x: ev.clientX, y: ev.clientY, item: { ...item } };
        const cell = this._cellSize();
        el.classList.add("o_axs_dragging");
        const onMove = (e) => {
            const dx = Math.round((e.clientX - start.x) / (cell.col + GAP));
            const dy = Math.round((e.clientY - start.y) / (cell.row + GAP));
            if (mode === "move") {
                item.x = Math.max(0, Math.min(COLS - item.w, start.item.x + dx));
                item.y = Math.max(0, start.item.y + dy);
            } else {
                item.w = Math.max(1, Math.min(COLS - item.x, start.item.w + dx));
                item.h = Math.max(1, Math.min(12, start.item.h + dy));
            }
            this._placeEl(el, item);
        };
        const onUp = () => {
            handle.removeEventListener("pointermove", onMove);
            handle.removeEventListener("pointerup", onUp);
            handle.removeEventListener("pointercancel", onUp);
            el.classList.remove("o_axs_dragging");
            if (item.x !== start.item.x || item.y !== start.item.y || item.w !== start.item.w || item.h !== start.item.h) {
                this._compact(item);
                this.saveLayout();
            }
        };
        handle.addEventListener("pointermove", onMove);
        handle.addEventListener("pointerup", onUp);
        handle.addEventListener("pointercancel", onUp);
    }

    /** Push overlapping items down, the moved item keeps its place. */
    _compact(moved) {
        const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
        const placed = [moved];
        const others = this.data.items.filter((i) => i !== moved).sort((a, b) => a.y - b.y || a.x - b.x);
        for (const item of others) {
            while (placed.some((p) => overlaps(p, item))) {
                item.y += 1;
            }
            placed.push(item);
        }
        // pull items up when there is room above them
        const sorted = [...this.data.items].sort((a, b) => a.y - b.y || a.x - b.x);
        const settled = [];
        for (const item of sorted) {
            while (item.y > 0 && !settled.some((p) => overlaps(p, { ...item, y: item.y - 1 }))) {
                item.y -= 1;
            }
            settled.push(item);
        }
        for (const item of this.data.items) {
            this._placeEl(this.itemEls[item.id], item);
        }
    }

    async saveLayout() {
        const layout = this.data.items.map((i) => ({ id: i.id, x: i.x, y: i.y, w: i.w, h: i.h }));
        try {
            await this.options.rpc("/axs_dashboard/layout", { dashboard_id: this.data.id, layout });
            this._onResize();
        } catch (error) {
            this._notify(error.message, "danger");
        }
    }

    // ------------------------------------------------------------------ export
    exportCsv(item) {
        const data = item.data || {};
        let rows;
        if (item.type === "list" && data.grouped) {
            rows = [data.columns, ...data.rows.map((r) => [r.label, r.value])];
        } else if (item.type === "list") {
            rows = [data.columns.map((c) => c.label), ...data.rows.map((r) => r.cells)];
        } else if (item.type === "gauge") {
            rows = [[item.name, _t("Target")], [data.value, data.target || ""]];
        } else {
            rows = [["", ...data.datasets.map((d) => d.label)], ...data.labels.map((label, i) => [label, ...data.datasets.map((d) => d.values[i])])];
        }
        const csv = rows.map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
        downloadBlob(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }), `${slugify(item.name)}.csv`);
    }

    exportPng(item, el) {
        const svg = el.querySelector("svg.o_axs_svg");
        if (!svg) {
            return;
        }
        const clone = svg.cloneNode(true);
        const styles = getComputedStyle(this.el);
        const text = styles.getPropertyValue("--axs-text").trim() || "#374151";
        const muted = styles.getPropertyValue("--axs-muted").trim() || "#6b7280";
        const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
        style.textContent = `text{font-family:Inter,Roboto,Arial,sans-serif;font-size:11px;fill:${muted}}
            .o_axs_value,.o_axs_center_value,.o_axs_gauge_value{fill:${text};font-weight:600}
            .o_axs_center_value{font-size:18px}.o_axs_gauge_value{font-size:22px}
            .o_axs_slice_label{fill:#fff;font-weight:600}.o_axs_grid{stroke:#e5e7eb}.o_axs_zero{stroke:#9ca3af}
            .o_axs_target{stroke:#dc2626;stroke-dasharray:5 4}.o_axs_gauge_track{fill:#e5e7eb}.o_axs_empty_ring{fill:#f3f4f6}
            .o_axs_slice{stroke:#fff;stroke-width:1.5}`;
        clone.insertBefore(style, clone.firstChild);
        const width = Number(svg.getAttribute("width"));
        const height = Number(svg.getAttribute("height"));
        const titleHeight = 34;
        const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
            const scale = 2;
            const canvas = document.createElement("canvas");
            canvas.width = width * scale;
            canvas.height = (height + titleHeight) * scale;
            const c = canvas.getContext("2d");
            c.scale(scale, scale);
            c.fillStyle = "#ffffff";
            c.fillRect(0, 0, width, height + titleHeight);
            c.fillStyle = "#111827";
            c.font = "600 14px Inter, Roboto, Arial, sans-serif";
            c.fillText(item.name, 8, 22);
            c.drawImage(img, 0, titleHeight, width, height);
            URL.revokeObjectURL(url);
            canvas.toBlob((png) => png && downloadBlob(png, `${slugify(item.name)}.png`), "image/png");
        };
        img.src = url;
    }
}
