/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class DdfscQualityDashboard extends Component {
    static template = "ddfsc_quality.QualityDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, data: null });
        onWillStart(() => this.refresh());
    }

    async refresh() {
        this.state.loading = true;
        this.state.data = await this.orm.call("ddfsc.quality.dashboard", "get_dashboard_data", []);
        this.state.loading = false;
    }

    openLots(name, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "stock.lot",
            views: [[false, "list"], [false, "pivot"], [false, "graph"], [false, "form"]],
            domain,
        });
    }

    openNcrs(name, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "ddfsc.quality.nonconformance",
            views: [[false, "list"], [false, "pivot"], [false, "graph"], [false, "form"]],
            domain,
        });
    }

    openLot(lotId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "QC Lot",
            res_model: "stock.lot",
            views: [[false, "form"]],
            res_id: lotId,
        });
    }

    openNcr(ncrId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Non-Conformance",
            res_model: "ddfsc.quality.nonconformance",
            views: [[false, "form"]],
            res_id: ncrId,
        });
    }
}

registry.category("actions").add("ddfsc_quality.quality_dashboard", DdfscQualityDashboard);
