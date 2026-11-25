/** @odoo-module **/
// Number formatting and small helpers shared by the website and the back end.

const formatters = new Map();

function getFormatter(locale, options) {
    const key = locale + JSON.stringify(options);
    if (!formatters.has(key)) {
        try {
            formatters.set(key, new Intl.NumberFormat(locale, options));
        } catch {
            formatters.set(key, new Intl.NumberFormat("en-US", options));
        }
    }
    return formatters.get(key);
}

/**
 * Format a number following an item's format settings.
 * @param {number} value
 * @param {Object} fmt {decimals, style, prefix, suffix, currency: {symbol, position}}
 * @param {string} locale BCP 47 tag, e.g. "en-US"
 * @param {Object} [opts] {short: true} forces the compact notation (axis labels)
 */
export function formatNumber(value, fmt = {}, locale = "en-US", opts = {}) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "";
    }
    const decimals = Math.max(0, Math.min(6, fmt.decimals || 0));
    let text;
    const style = opts.short ? "compact" : fmt.style || "standard";
    if (style === "compact") {
        text = getFormatter(locale, {
            notation: "compact",
            maximumFractionDigits: Math.max(decimals, Math.abs(value) >= 1000 ? 1 : 0),
        }).format(value);
    } else if (style === "indian") {
        text = getFormatter("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);
    } else if (style === "exact") {
        text = getFormatter(locale, { useGrouping: false, maximumFractionDigits: 6 }).format(value);
    } else {
        text = getFormatter(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);
    }
    if (fmt.currency && fmt.currency.symbol) {
        text = fmt.currency.position === "before" ? `${fmt.currency.symbol} ${text}` : `${text} ${fmt.currency.symbol}`;
    }
    return `${fmt.prefix || ""}${text}${fmt.suffix || ""}`;
}

export function formatPercent(value, locale = "en-US", decimals = 1) {
    return getFormatter(locale, { maximumFractionDigits: decimals, minimumFractionDigits: 0 }).format(value) + "%";
}

/** "Nice" axis bounds and ticks for values between min and max. */
export function niceTicks(min, max, count = 5) {
    if (min === max) {
        max = min === 0 ? 1 : min + Math.abs(min) * 0.5;
        min = Math.min(0, min);
    }
    const span = max - min;
    const raw = span / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
    const lo = Math.floor(min / step) * step;
    const hi = Math.ceil(max / step) * step;
    const ticks = [];
    for (let v = lo; v <= hi + step / 2; v += step) {
        ticks.push(Math.round(v / step) * step);
    }
    return { min: lo, max: hi, ticks };
}

export function escapeHtml(text) {
    return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

/** Mix a hex color with white (amount > 0) or black (amount < 0). */
export function shade(hex, amount) {
    const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex || "");
    if (!m) {
        return hex;
    }
    let h = m[1];
    if (h.length === 3) {
        h = h.split("").map((c) => c + c).join("");
    }
    const n = parseInt(h, 16);
    let [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    const target = amount > 0 ? 255 : 0;
    const t = Math.abs(amount);
    [r, g, b] = [r, g, b].map((c) => Math.round(c + (target - c) * t));
    return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
}

/** Readable text color (black or white) for a background. */
export function contrastColor(hex) {
    const c = shade(hex, 0).replace("#", "");
    if (c.length !== 6) {
        return "#ffffff";
    }
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16));
    return (r * 299 + g * 587 + b * 114) / 1000 > 150 ? "#1f2937" : "#ffffff";
}

export function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function slugify(text) {
    return String(text || "export").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "export";
}

export const PALETTES = {
    axsync: ["#3a6ea5", "#e8875b", "#5b8c5a", "#8e6c8a", "#d4a537", "#4fa3a5", "#c8553d", "#6b7a99"],
    ocean: ["#1d6fa3", "#2a9d8f", "#48b5c4", "#264653", "#8ab17d", "#e9c46a", "#5e60ce", "#7aa6c2"],
    sunset: ["#e76f51", "#f4a261", "#e9c46a", "#d62828", "#9d4edd", "#f77f00", "#bc6c25", "#6d597a"],
    forest: ["#2d6a4f", "#52796f", "#95d5b2", "#bc4749", "#a7c957", "#386641", "#dda15e", "#6a994e"],
    berry: ["#8e44ad", "#c0392b", "#16a085", "#d35400", "#2980b9", "#e84393", "#6c5ce7", "#00b894"],
    mono: ["#34495e", "#5d6d7e", "#85929e", "#aeb6bf", "#2c3e50", "#7f8c8d", "#95a5a6", "#566573"],
};
