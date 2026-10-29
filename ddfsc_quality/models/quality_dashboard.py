from odoo import api, fields, models


class DdfscQualityDashboard(models.Model):
    """A read-only operational overview for the factory QC workflow."""

    _name = "ddfsc.quality.dashboard"
    _description = "DDFSC Quality Control Dashboard"

    name = fields.Char(default="Quality Control Overview", readonly=True)
    awaiting_review_count = fields.Integer(compute="_compute_metrics")
    data_entry_count = fields.Integer(compute="_compute_metrics")
    blocked_lot_count = fields.Integer(compute="_compute_metrics")
    approved_lot_count = fields.Integer(compute="_compute_metrics")
    open_ncr_count = fields.Integer(compute="_compute_metrics")
    overdue_ncr_count = fields.Integer(compute="_compute_metrics")
    critical_ncr_count = fields.Integer(compute="_compute_metrics")
    awaiting_review_lot_ids = fields.Many2many("stock.lot", compute="_compute_metrics")
    blocked_lot_ids = fields.Many2many("stock.lot", compute="_compute_metrics")
    recently_approved_lot_ids = fields.Many2many("stock.lot", compute="_compute_metrics")
    open_ncr_ids = fields.Many2many("ddfsc.quality.nonconformance", compute="_compute_metrics")

    def _compute_metrics(self):
        Lot = self.env["stock.lot"]
        Nonconformance = self.env["ddfsc.quality.nonconformance"]
        submitted_domain = [("ddfsc_review_state", "=", "submitted")]
        draft_domain = [("ddfsc_review_state", "=", "draft"), ("ddfsc_quality_state", "=", "pending")]
        blocked_domain = [("ddfsc_quality_state", "in", ("hold", "rejected"))]
        approved_domain = [("ddfsc_quality_state", "in", ("pass", "released"))]
        open_ncr_domain = [("state", "not in", ("closed", "canceled"))]

        for dashboard in self:
            dashboard.awaiting_review_count = Lot.search_count(submitted_domain)
            dashboard.data_entry_count = Lot.search_count(draft_domain)
            dashboard.blocked_lot_count = Lot.search_count(blocked_domain)
            dashboard.approved_lot_count = Lot.search_count(approved_domain)
            dashboard.open_ncr_count = Nonconformance.search_count(open_ncr_domain)
            dashboard.overdue_ncr_count = Nonconformance.search_count(open_ncr_domain + [("is_overdue", "=", True)])
            dashboard.critical_ncr_count = Nonconformance.search_count(open_ncr_domain + [("severity", "=", "critical")])
            dashboard.awaiting_review_lot_ids = Lot.search(submitted_domain, order="quality_submitted_date asc, id asc", limit=8)
            dashboard.blocked_lot_ids = Lot.search(blocked_domain, order="quality_reviewed_date desc, id desc", limit=8)
            dashboard.recently_approved_lot_ids = Lot.search(approved_domain, order="quality_reviewed_date desc, id desc", limit=8)
            dashboard.open_ncr_ids = Nonconformance.search(open_ncr_domain, order="due_date asc nulls last, create_date desc", limit=8)

    @staticmethod
    def _lot_action(name, domain):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "stock.lot",
            "view_mode": "list,pivot,graph,form",
            "domain": domain,
        }

    @staticmethod
    def _ncr_action(name, domain):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "ddfsc.quality.nonconformance",
            "view_mode": "list,pivot,graph,form",
            "domain": domain,
        }

    def action_open_awaiting_review(self):
        return self._lot_action("QC Lots Awaiting Review", [("ddfsc_review_state", "=", "submitted")])

    def action_open_data_entry(self):
        return self._lot_action("QC Lots in Data Entry", [("ddfsc_review_state", "=", "draft"), ("ddfsc_quality_state", "=", "pending")])

    def action_open_blocked_lots(self):
        return self._lot_action("Blocked QC Lots", [("ddfsc_quality_state", "in", ("hold", "rejected"))])

    def action_open_approved_lots(self):
        return self._lot_action("Approved QC Lots", [("ddfsc_quality_state", "in", ("pass", "released"))])

    def action_open_ncrs(self):
        return self._ncr_action("Open Non-Conformances", [("state", "not in", ("closed", "canceled"))])

    def action_open_overdue_ncrs(self):
        return self._ncr_action(
            "Overdue Non-Conformances",
            [("state", "not in", ("closed", "canceled")), ("is_overdue", "=", True)],
        )

    @api.model
    def get_dashboard_data(self):
        """Return compact, user-accessible data for the Quality Overview UI."""
        Lot = self.env["stock.lot"]
        Nonconformance = self.env["ddfsc.quality.nonconformance"]
        status_definitions = [
            ("pending", "Pending", "warning"),
            ("pass", "Approved", "success"),
            ("hold", "On Hold", "danger"),
            ("rejected", "Rejected", "danger"),
            ("released", "Exception Release", "info"),
        ]
        checkpoint_labels = dict(Lot.fields_get(["quality_checkpoint"])["quality_checkpoint"]["selection"])
        severity_labels = dict(Nonconformance._fields["severity"].selection)
        open_ncr_domain = [("state", "not in", ("closed", "canceled"))]
        total_governed = Lot.search_count([("quality_plan_id", "!=", False)])
        approved_count = Lot.search_count([("ddfsc_quality_state", "in", ("pass", "released"))])
        status_data = [
            {"key": key, "label": label, "tone": tone, "count": Lot.search_count([("ddfsc_quality_state", "=", key)])}
            for key, label, tone in status_definitions
        ]
        checkpoint_data = []
        for checkpoint, label in checkpoint_labels.items():
            count = Lot.search_count([("quality_checkpoint", "=", checkpoint)])
            if count:
                checkpoint_data.append({"key": checkpoint, "label": label, "count": count})
        severity_data = [
            {"key": key, "label": label, "count": Nonconformance.search_count(open_ncr_domain + [("severity", "=", key)])}
            for key, label in severity_labels.items()
        ]
        max_checkpoint = max([item["count"] for item in checkpoint_data] or [1])
        max_severity = max([item["count"] for item in severity_data] or [1]) or 1
        for item in checkpoint_data:
            item["percent"] = round(item["count"] * 100 / max_checkpoint)
        for item in severity_data:
            item["percent"] = round(item["count"] * 100 / max_severity)

        def lot_rows(records):
            return [{
                "id": lot.id,
                "name": lot.name,
                "product": lot.product_id.display_name,
                "checkpoint": checkpoint_labels.get(lot.quality_checkpoint, "Not assigned"),
                "status": dict(Lot._fields["ddfsc_quality_state"].selection).get(lot.ddfsc_quality_state),
                "status_key": lot.ddfsc_quality_state,
                "progress": lot.ddfsc_quality_progress or "—",
            } for lot in records]

        review_lots = Lot.search([( "ddfsc_review_state", "=", "submitted")], order="quality_submitted_date asc, id asc", limit=6)
        blocked_lots = Lot.search([( "ddfsc_quality_state", "in", ("hold", "rejected"))], order="quality_reviewed_date desc, id desc", limit=6)
        open_ncrs = Nonconformance.search(open_ncr_domain, order="due_date asc nulls last, create_date desc", limit=6)
        return {
            "metrics": {
                "awaiting_review": Lot.search_count([( "ddfsc_review_state", "=", "submitted")]),
                "data_entry": Lot.search_count([( "ddfsc_review_state", "=", "draft"), ("ddfsc_quality_state", "=", "pending")]),
                "blocked": Lot.search_count([( "ddfsc_quality_state", "in", ("hold", "rejected"))]),
                "approved": approved_count,
                "open_ncr": Nonconformance.search_count(open_ncr_domain),
                "overdue_ncr": Nonconformance.search_count(open_ncr_domain + [("is_overdue", "=", True)]),
            },
            "release_rate": round(approved_count * 100 / total_governed) if total_governed else 0,
            "governed_lots": total_governed,
            "status_data": status_data,
            "checkpoint_data": checkpoint_data,
            "severity_data": severity_data,
            "review_lots": lot_rows(review_lots),
            "blocked_lots": lot_rows(blocked_lots),
            "open_ncrs": [{
                "id": item.id,
                "name": item.name,
                "lot": item.lot_id.name,
                "product": item.product_id.display_name,
                "severity": severity_labels.get(item.severity),
                "severity_key": item.severity,
                "owner": item.owner_id.display_name,
                "state": dict(Nonconformance._fields["state"].selection).get(item.state),
                "overdue": item.is_overdue,
            } for item in open_ncrs],
        }
