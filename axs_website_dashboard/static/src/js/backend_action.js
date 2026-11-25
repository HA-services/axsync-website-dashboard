/** @odoo-module **/
// Back-end client action "axs_website_dashboard.dashboard": shows a dashboard with editing tools.

import { Component, onMounted, onWillUnmount, signal, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { DashboardEngine } from "./dashboard_engine";

export class AxsDashboardAction extends Component {
    static template = "axs_website_dashboard.DashboardAction";
    props = useProps({ ...standardActionServiceProps });
    root = signal.ref();

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        onMounted(() => this.mount());
        onWillUnmount(() => this.engine && this.engine.destroy());
    }

    get dashboardId() {
        const params = (this.props.action && this.props.action.params) || {};
        const context = (this.props.action && this.props.action.context) || {};
        return params.dashboard_id || context.dashboard_id || context.active_id;
    }

    mount() {
        const reload = () => this.engine && this.engine.load();
        this.engine = new DashboardEngine(this.root(), {
            dashboardId: this.dashboardId,
            channel: "backend",
            notify: (message, type) => this.notification.add(message, { type }),
            onOpenRecords: ({ model, domain, name, resId }) => {
                if (resId) {
                    this.action.doAction({ type: "ir.actions.act_window", res_model: model, res_id: resId, views: [[false, "form"]] });
                } else {
                    this.action.doAction({ type: "ir.actions.act_window", name, res_model: model, domain, views: [[false, "list"], [false, "form"]] });
                }
            },
            onEditItem: (id) => {
                this.action.doAction(
                    { type: "ir.actions.act_window", res_model: "axs.dashboard.item", res_id: id, views: [[false, "form"]], target: "new" },
                    { onClose: reload }
                );
            },
            onAddItem: (slot) => {
                this.action.doAction(
                    {
                        type: "ir.actions.act_window",
                        res_model: "axs.dashboard.item",
                        views: [[false, "form"]],
                        target: "new",
                        context: { default_dashboard_id: this.dashboardId, default_grid_x: slot.x, default_grid_y: slot.y, default_grid_w: slot.w, default_grid_h: slot.h },
                    },
                    { onClose: reload }
                );
            },
            onOpenSettings: () => {
                this.action.doAction(
                    { type: "ir.actions.act_window", res_model: "axs.dashboard", res_id: this.dashboardId, views: [[false, "form"]], target: "new" },
                    { onClose: reload }
                );
            },
        });
        if (!this.dashboardId) {
            this.root().innerHTML = '<div class="o_axs_message">No dashboard selected.</div>';
            return;
        }
        this.engine.start();
    }
}

registry.category("actions").add("axs_website_dashboard.dashboard", AxsDashboardAction);
