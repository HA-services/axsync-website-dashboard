/** @odoo-module **/
// Website: mount every element carrying data-axs-dashboard="<id>" (dashboard pages and embed codes).

import { DashboardEngine } from "./dashboard_engine";

const engines = new WeakMap();

function mountAll(root = document) {
    for (const el of root.querySelectorAll("[data-axs-dashboard]")) {
        if (engines.has(el)) {
            continue;
        }
        const dashboardId = parseInt(el.dataset.axsDashboard, 10);
        if (!dashboardId) {
            continue;
        }
        // content saved by the website editor inside an embed is replaced by the live dashboard
        el.innerHTML = "";
        const engine = new DashboardEngine(el, {
            dashboardId,
            channel: "website",
            compactHeader: !el.dataset.axsPage,
        });
        engines.set(el, engine);
        engine.start();
    }
}

function boot() {
    mountAll();
    // embeds added later (website builder, lazy content)
    const observer = new MutationObserver((mutations) => {
        for (const m of mutations) {
            for (const node of m.addedNodes) {
                if (node.nodeType === 1 && (node.matches("[data-axs-dashboard]") || node.querySelector("[data-axs-dashboard]"))) {
                    mountAll(node.parentElement || document);
                    return;
                }
            }
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
} else {
    boot();
}
