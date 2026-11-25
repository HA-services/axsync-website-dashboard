/** @odoo-module **/
// SVG charts drawn by AXSync Website Dashboard (no chart library needed, identical on every Odoo version).

import { escapeHtml, formatNumber, formatPercent, niceTicks } from "./format";

const CARTESIAN = ["bar", "stacked_bar", "line", "area", "hbar"];
const CIRCULAR = ["pie", "doughnut", "polar"];

function truncate(text, max) {
    text = String(text ?? "");
    return text.length > max ? text.slice(0, Math.max(1, max - 1)) + "…" : text;
}

function approxWidth(text, size = 11) {
    return String(text ?? "").length * size * 0.56;
}

function arcPath(cx, cy, r0, r1, a0, a1) {
    // angles in radians, 0 = 12 o'clock, clockwise
    if (a1 - a0 >= Math.PI * 2 - 1e-6) {
        a1 = a0 + Math.PI * 2 - 1e-4;
    }
    const p = (r, a) => [cx + r * Math.sin(a), cy - r * Math.cos(a)];
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const [x0, y0] = p(r1, a0);
    const [x1, y1] = p(r1, a1);
    if (r0 <= 0) {
        return `M${cx},${cy} L${x0},${y0} A${r1},${r1} 0 ${large} 1 ${x1},${y1} Z`;
    }
    const [x2, y2] = p(r0, a1);
    const [x3, y3] = p(r0, a0);
    return `M${x0},${y0} A${r1},${r1} 0 ${large} 1 ${x1},${y1} L${x2},${y2} A${r0},${r0} 0 ${large} 0 ${x3},${y3} Z`;
}

function legendHtml(entries, hidden) {
    return entries
        .map(
            (e, i) => `<button type="button" class="o_axs_legend_entry ${hidden.has(i) ? "o_axs_off" : ""}" data-legend="${i}" title="${escapeHtml(e.label)}">
                <span class="o_axs_swatch" style="background:${e.color}"></span><span>${escapeHtml(truncate(e.label, 28))}</span></button>`
        )
        .join("");
}

/**
 * Draw a chart in ``host``.
 * @param {HTMLElement} host
 * @param {Object} item item configuration (type, format, show_values, show_legend, show_percent)
 * @param {Object} data {labels, datasets: [{label, values}], target}
 * @param {Object} ctx {palette, locale, hidden: Set, onToggle(i), onSegment(i), tooltip: {show, hide}}
 */
export function drawChart(host, item, data, ctx) {
    host.innerHTML = "";
    const type = item.type;
    const labels = data.labels || [];
    const datasets = data.datasets || [];
    const circular = CIRCULAR.includes(type);
    const palette = ctx.palette;
    const colorFor = (i) => (datasets.length === 1 && !circular && item.color ? (i === 0 ? item.color : palette[i % palette.length]) : palette[i % palette.length]);
    const legendEntries = circular
        ? labels.map((label, i) => ({ label, color: palette[i % palette.length] }))
        : datasets.map((d, i) => ({ label: d.label, color: colorFor(i) }));
    const showLegend = item.show_legend && (circular || datasets.length > 1);

    const plot = document.createElement("div");
    plot.className = "o_axs_chart_plot";
    host.appendChild(plot);
    if (showLegend) {
        const legend = document.createElement("div");
        legend.className = "o_axs_legend";
        legend.innerHTML = legendHtml(legendEntries, ctx.hidden);
        legend.addEventListener("click", (ev) => {
            const btn = ev.target.closest("[data-legend]");
            if (btn) {
                ctx.onToggle(Number(btn.dataset.legend));
            }
        });
        host.appendChild(legend);
    }
    const W = Math.max(120, plot.clientWidth);
    const H = Math.max(90, plot.clientHeight);
    let svg;
    if (circular) {
        svg = drawCircular(W, H, item, labels, datasets[0] ? datasets[0].values : [], ctx);
    } else if (type === "radar") {
        svg = drawRadar(W, H, item, labels, datasets, ctx, colorFor);
    } else if (CARTESIAN.includes(type)) {
        svg = drawCartesian(W, H, item, labels, datasets, data.target, ctx, colorFor);
    } else {
        svg = "";
    }
    plot.innerHTML = svg;
    const svgEl = plot.querySelector("svg");
    if (!svgEl) {
        return null;
    }
    svgEl.addEventListener("mousemove", (ev) => {
        const target = ev.target.closest("[data-tip]");
        if (target) {
            ctx.tooltip.show(target.getAttribute("data-tip"), ev);
        } else {
            ctx.tooltip.hide();
        }
    });
    svgEl.addEventListener("mouseleave", () => ctx.tooltip.hide());
    svgEl.addEventListener("click", (ev) => {
        const target = ev.target.closest("[data-i]");
        if (target && ctx.onSegment) {
            ctx.onSegment(Number(target.dataset.i), Number(target.dataset.d || 0));
        }
    });
    return svgEl;
}

function tip(title, label, value) {
    return escapeHtml(`<div class="o_axs_tip_title">${escapeHtml(title)}</div><div><b>${escapeHtml(value)}</b>${label ? " · " + escapeHtml(label) : ""}</div>`);
}

function drawCartesian(W, H, item, labels, datasets, target, ctx, colorFor) {
    const fmt = (v, short) => formatNumber(v, item.format, ctx.locale, { short });
    const type = item.type;
    const horizontal = type === "hbar";
    const stacked = type === "stacked_bar";
    const visible = datasets.map((d, i) => ({ ...d, index: i })).filter((d) => !ctx.hidden.has(d.index));
    const n = labels.length;
    let lo = 0;
    let hi = 0;
    for (let i = 0; i < n; i++) {
        if (stacked) {
            let pos = 0;
            let neg = 0;
            for (const d of visible) {
                const v = d.values[i] || 0;
                if (v >= 0) {
                    pos += v;
                } else {
                    neg += v;
                }
            }
            hi = Math.max(hi, pos);
            lo = Math.min(lo, neg);
        } else {
            for (const d of visible) {
                hi = Math.max(hi, d.values[i] || 0);
                lo = Math.min(lo, d.values[i] || 0);
            }
        }
    }
    if (target) {
        hi = Math.max(hi, target);
    }
    const scale = niceTicks(lo, hi, horizontal ? Math.max(2, Math.floor(W / 110)) : Math.max(2, Math.floor(H / 45)));
    const tickLabels = scale.ticks.map((t) => fmt(t, true));
    const parts = [];
    let left;
    let right = 12;
    let top = 10;
    let bottom;
    if (horizontal) {
        const maxLabel = Math.max(...labels.map((l) => approxWidth(l)), 20);
        left = Math.min(W * 0.38, maxLabel + 12);
        bottom = 24;
    } else {
        left = Math.max(...tickLabels.map((t) => approxWidth(t, 10)), 16) + 12;
        bottom = 26;
    }
    // x labels for vertical charts: show 1 label every `every` slots
    let every = 1;
    let maxChars = 18;
    if (!horizontal && n) {
        const slot = (W - left - right) / n;
        const longest = Math.max(...labels.map((l) => String(l).length), 1);
        maxChars = Math.max(3, Math.floor((slot * Math.max(1, every)) / 6));
        every = Math.max(1, Math.ceil((Math.min(longest, 14) * 6.2) / Math.max(slot, 1)));
        maxChars = Math.max(4, Math.floor((slot * every) / 6.2));
    }
    const pw = Math.max(10, W - left - right);
    const ph = Math.max(10, H - top - bottom);
    const valueToPx = (v) => ((v - scale.min) / (scale.max - scale.min || 1)) * (horizontal ? pw : ph);
    // grid and axis labels
    for (let k = 0; k < scale.ticks.length; k++) {
        const t = scale.ticks[k];
        if (horizontal) {
            const x = left + valueToPx(t);
            parts.push(`<line class="o_axs_grid" x1="${x}" y1="${top}" x2="${x}" y2="${top + ph}"/>`);
            parts.push(`<text class="o_axs_axis" x="${x}" y="${top + ph + 16}" text-anchor="middle">${escapeHtml(tickLabels[k])}</text>`);
        } else {
            const y = top + ph - valueToPx(t);
            parts.push(`<line class="o_axs_grid" x1="${left}" y1="${y}" x2="${left + pw}" y2="${y}"/>`);
            parts.push(`<text class="o_axs_axis" x="${left - 6}" y="${y + 3.5}" text-anchor="end">${escapeHtml(tickLabels[k])}</text>`);
        }
    }
    const band = (horizontal ? ph : pw) / Math.max(1, n);
    const zero = valueToPx(0);
    const showValues = item.show_values && band >= (horizontal ? 14 : 22);
    if (type === "line" || type === "area") {
        visible.forEach((d) => {
            const color = colorFor(d.index);
            const pts = labels.map((_, i) => [left + band * (i + 0.5), top + ph - valueToPx(d.values[i] || 0)]);
            if (!pts.length) {
                return;
            }
            const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
            if (type === "area") {
                parts.push(`<path d="${line} L${pts[pts.length - 1][0]},${top + ph - zero} L${pts[0][0]},${top + ph - zero} Z" fill="${color}" fill-opacity="0.16" stroke="none"/>`);
            }
            parts.push(`<path d="${line}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>`);
            pts.forEach((p, i) => {
                const value = fmt(d.values[i] || 0);
                parts.push(`<circle class="o_axs_hit" cx="${p[0]}" cy="${p[1]}" r="${n > 40 ? 2.5 : 4}" fill="${color}" data-i="${i}" data-d="${d.index}" data-tip="${tip(labels[i], visible.length > 1 ? d.label : "", value)}"/>`);
                if (showValues) {
                    parts.push(`<text class="o_axs_value" x="${p[0]}" y="${p[1] - 8}" text-anchor="middle">${escapeHtml(fmt(d.values[i] || 0, true))}</text>`);
                }
            });
        });
    } else {
        const groupW = band * 0.72;
        const barW = stacked ? groupW : groupW / Math.max(1, visible.length);
        for (let i = 0; i < n; i++) {
            let posAcc = 0;
            let negAcc = 0;
            visible.forEach((d, j) => {
                const v = d.values[i] || 0;
                const color = colorFor(d.index);
                let from;
                let to;
                if (stacked) {
                    from = v >= 0 ? posAcc : negAcc;
                    to = from + v;
                    if (v >= 0) {
                        posAcc = to;
                    } else {
                        negAcc = to;
                    }
                } else {
                    from = 0;
                    to = v;
                }
                const a = valueToPx(Math.min(from, to));
                const b = valueToPx(Math.max(from, to));
                const offset = band * i + (band - groupW) / 2 + (stacked ? 0 : barW * j);
                const t = tip(labels[i], visible.length > 1 ? d.label : "", fmt(v));
                const size = Math.max(b - a, v ? 1 : 0);
                if (horizontal) {
                    parts.push(`<rect class="o_axs_hit" x="${left + a}" y="${top + offset}" width="${size}" height="${Math.max(1, barW - 1)}" rx="2" fill="${color}" data-i="${i}" data-d="${d.index}" data-tip="${t}"/>`);
                    if (showValues && !stacked) {
                        parts.push(`<text class="o_axs_value" x="${left + b + 4}" y="${top + offset + barW / 2 + 3.5}">${escapeHtml(fmt(v, true))}</text>`);
                    }
                } else {
                    parts.push(`<rect class="o_axs_hit" x="${left + offset}" y="${top + ph - b}" width="${Math.max(1, barW - 1)}" height="${size}" rx="2" fill="${color}" data-i="${i}" data-d="${d.index}" data-tip="${t}"/>`);
                    if (showValues && !stacked && barW > 16) {
                        parts.push(`<text class="o_axs_value" x="${left + offset + barW / 2}" y="${top + ph - b - 5}" text-anchor="middle">${escapeHtml(fmt(v, true))}</text>`);
                    }
                }
            });
            if (showValues && stacked && visible.length) {
                const total = posAcc + negAcc;
                const b = valueToPx(Math.max(posAcc, 0));
                if (horizontal) {
                    parts.push(`<text class="o_axs_value" x="${left + b + 4}" y="${top + band * i + band / 2 + 3.5}">${escapeHtml(fmt(total, true))}</text>`);
                } else {
                    parts.push(`<text class="o_axs_value" x="${left + band * i + band / 2}" y="${top + ph - b - 5}" text-anchor="middle">${escapeHtml(fmt(total, true))}</text>`);
                }
            }
        }
    }
    // category labels
    for (let i = 0; i < n; i++) {
        if (horizontal) {
            parts.push(`<text class="o_axs_axis o_axs_cat" x="${left - 6}" y="${top + band * i + band / 2 + 3.5}" text-anchor="end">${escapeHtml(truncate(labels[i], Math.floor(left / 6)))}<title>${escapeHtml(labels[i])}</title></text>`);
        } else if (i % every === 0) {
            parts.push(`<text class="o_axs_axis o_axs_cat" x="${left + band * (i + 0.5)}" y="${top + ph + 16}" text-anchor="middle">${escapeHtml(truncate(labels[i], maxChars))}<title>${escapeHtml(labels[i])}</title></text>`);
        }
    }
    // axis line on zero, target line
    if (horizontal) {
        parts.push(`<line class="o_axs_zero" x1="${left + zero}" y1="${top}" x2="${left + zero}" y2="${top + ph}"/>`);
    } else {
        parts.push(`<line class="o_axs_zero" x1="${left}" y1="${top + ph - zero}" x2="${left + pw}" y2="${top + ph - zero}"/>`);
    }
    if (target) {
        const t = valueToPx(target);
        if (horizontal) {
            parts.push(`<line class="o_axs_target" x1="${left + t}" y1="${top}" x2="${left + t}" y2="${top + ph}"/><text class="o_axs_target_label" x="${left + t - 4}" y="${top + 10}" text-anchor="end">${escapeHtml(fmt(target, true))}</text>`);
        } else {
            parts.push(`<line class="o_axs_target" x1="${left}" y1="${top + ph - t}" x2="${left + pw}" y2="${top + ph - t}"/><text class="o_axs_target_label" x="${left + pw}" y="${top + ph - t - 5}" text-anchor="end">${escapeHtml(fmt(target, true))}</text>`);
        }
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" class="o_axs_svg">${parts.join("")}</svg>`;
}

function drawCircular(W, H, item, labels, values, ctx) {
    const fmt = (v) => formatNumber(v, item.format, ctx.locale);
    const type = item.type;
    const cx = W / 2;
    const cy = H / 2;
    const r = Math.max(10, Math.min(W, H) / 2 - 8);
    const inner = type === "doughnut" ? r * 0.58 : 0;
    const shown = values.map((v, i) => (ctx.hidden.has(i) ? 0 : Math.max(0, v || 0)));
    const total = shown.reduce((a, b) => a + b, 0);
    const parts = [];
    if (!total) {
        parts.push(`<circle cx="${cx}" cy="${cy}" r="${r}" class="o_axs_empty_ring"/>`);
    }
    const max = Math.max(...shown, 0);
    const count = shown.filter((v) => v > 0).length;
    let angle = 0;
    shown.forEach((v, i) => {
        if (!v) {
            return;
        }
        let a0;
        let a1;
        let radius = r;
        if (type === "polar") {
            a0 = angle;
            a1 = angle + (Math.PI * 2) / count;
            radius = Math.max(6, r * Math.sqrt(v / max));
        } else {
            a0 = angle;
            a1 = angle + (v / total) * Math.PI * 2;
        }
        angle = a1;
        const color = ctx.palette[i % ctx.palette.length];
        const pct = (v / total) * 100;
        const t = tip(labels[i], formatPercent(pct, ctx.locale), fmt(v));
        parts.push(`<path class="o_axs_hit o_axs_slice" d="${arcPath(cx, cy, inner, radius, a0, a1)}" fill="${color}" data-i="${i}" data-tip="${t}"/>`);
        const mid = (a0 + a1) / 2;
        const labelR = type === "polar" ? radius * 0.62 : inner ? (inner + r) / 2 : r * 0.64;
        if ((item.show_percent || item.show_values) && a1 - a0 > 0.32 && (type !== "polar" || radius > 26)) {
            const text = item.show_percent ? formatPercent(pct, ctx.locale, 0) : formatNumber(v, item.format, ctx.locale, { short: true });
            parts.push(`<text class="o_axs_slice_label" x="${cx + labelR * Math.sin(mid)}" y="${cy - labelR * Math.cos(mid) + 4}" text-anchor="middle">${escapeHtml(text)}</text>`);
        }
    });
    if (type === "doughnut" && total) {
        parts.push(`<text class="o_axs_center_value" x="${cx}" y="${cy + 2}" text-anchor="middle">${escapeHtml(formatNumber(total, item.format, ctx.locale, { short: true }))}</text>`);
        parts.push(`<text class="o_axs_center_label" x="${cx}" y="${cy + 18}" text-anchor="middle">${escapeHtml(item.measure_label || "")}</text>`);
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" class="o_axs_svg">${parts.join("")}</svg>`;
}

function drawRadar(W, H, item, labels, datasets, ctx, colorFor) {
    const fmt = (v, short) => formatNumber(v, item.format, ctx.locale, { short });
    const n = labels.length;
    const cx = W / 2;
    const cy = H / 2 + 4;
    const r = Math.max(10, Math.min(W / 2 - 60, H / 2 - 22));
    const visible = datasets.map((d, i) => ({ ...d, index: i })).filter((d) => !ctx.hidden.has(d.index));
    const max = Math.max(...visible.flatMap((d) => d.values), 0) || 1;
    const scale = niceTicks(0, max, 4);
    const parts = [];
    const point = (i, v) => {
        const a = (Math.PI * 2 * i) / Math.max(n, 1);
        const rr = (v / scale.max) * r;
        return [cx + rr * Math.sin(a), cy - rr * Math.cos(a)];
    };
    scale.ticks.slice(1).forEach((t) => {
        const ring = labels.map((_, i) => point(i, t).join(",")).join(" ");
        parts.push(`<polygon class="o_axs_grid" points="${ring}" fill="none"/>`);
    });
    labels.forEach((label, i) => {
        const [x, y] = point(i, scale.max);
        parts.push(`<line class="o_axs_grid" x1="${cx}" y1="${cy}" x2="${x}" y2="${y}"/>`);
        const [lx, ly] = point(i, scale.max * 1.12);
        const anchor = Math.abs(lx - cx) < 8 ? "middle" : lx > cx ? "start" : "end";
        parts.push(`<text class="o_axs_axis" x="${lx}" y="${ly + 4}" text-anchor="${anchor}">${escapeHtml(truncate(label, 16))}<title>${escapeHtml(label)}</title></text>`);
    });
    visible.forEach((d) => {
        const color = colorFor(d.index);
        const pts = labels.map((_, i) => point(i, d.values[i] || 0));
        parts.push(`<polygon points="${pts.map((p) => p.join(",")).join(" ")}" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2"/>`);
        pts.forEach((p, i) => {
            parts.push(`<circle class="o_axs_hit" cx="${p[0]}" cy="${p[1]}" r="3.5" fill="${color}" data-i="${i}" data-d="${d.index}" data-tip="${tip(labels[i], visible.length > 1 ? d.label : "", fmt(d.values[i] || 0))}"/>`);
        });
    });
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" class="o_axs_svg">${parts.join("")}</svg>`;
}

/** Half-circle gauge for a value against a target (or 100). */
export function drawGauge(host, item, data, ctx) {
    const W = Math.max(120, host.clientWidth);
    const H = Math.max(80, host.clientHeight);
    const target = data.target || 100;
    const ratio = Math.max(0, Math.min(1, (data.value || 0) / target));
    const r = Math.max(20, Math.min(W / 2 - 10, H - 34));
    const cx = W / 2;
    const cy = r + 10;
    const a0 = -Math.PI / 2;
    const color = item.color || ctx.palette[0];
    const value = formatNumber(data.value, item.format, ctx.locale);
    host.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" class="o_axs_svg">
        <path d="${arcPath(cx, cy, r * 0.72, r, a0, Math.PI / 2)}" class="o_axs_gauge_track"/>
        <path d="${arcPath(cx, cy, r * 0.72, r, a0, a0 + Math.PI * Math.max(ratio, 0.002))}" fill="${color}" class="o_axs_hit" data-tip="${tip(item.name, formatPercent((data.value / target) * 100, ctx.locale), value)}"/>
        <text class="o_axs_gauge_value" x="${cx}" y="${cy - 4}" text-anchor="middle">${escapeHtml(value)}</text>
        <text class="o_axs_center_label" x="${cx - r * 0.86}" y="${cy + 16}" text-anchor="middle">0</text>
        <text class="o_axs_center_label" x="${cx + r * 0.86}" y="${cy + 16}" text-anchor="middle">${escapeHtml(formatNumber(target, item.format, ctx.locale, { short: true }))}</text>
    </svg>`;
    const svgEl = host.querySelector("svg");
    svgEl.addEventListener("mousemove", (ev) => {
        const t = ev.target.closest("[data-tip]");
        if (t) {
            ctx.tooltip.show(t.getAttribute("data-tip"), ev);
        } else {
            ctx.tooltip.hide();
        }
    });
    svgEl.addEventListener("mouseleave", () => ctx.tooltip.hide());
    return svgEl;
}

export const CHART_TYPES = [...CARTESIAN, ...CIRCULAR, "radar"];
