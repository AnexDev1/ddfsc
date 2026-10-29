from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class DdfscQcInspection(models.Model):
    _name = "ddfsc.qc.inspection"
    _description = "DDFSC QC Inspection"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    lot_id = fields.Many2one("stock.lot", required=True, ondelete="restrict", index=True, tracking=True)
    product_id = fields.Many2one(related="lot_id.product_id", store=True, readonly=True)
    plan_id = fields.Many2one("ddfsc.quality.plan", required=True, ondelete="restrict", readonly=True)
    checkpoint = fields.Selection(related="plan_id.checkpoint", store=True, readonly=True)
    production_id = fields.Many2one("mrp.production", string="Manufacturing Order", readonly=True)
    receipt_id = fields.Many2one("stock.picking", string="Source Receipt", readonly=True)
    supplier_id = fields.Many2one("res.partner", string="Supplier", readonly=True)
    inspector_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    submitted_by_id = fields.Many2one("res.users", readonly=True)
    submitted_date = fields.Datetime(readonly=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_date = fields.Datetime(readonly=True)
    state = fields.Selection([
        ("draft", "Data Entry"), ("submitted", "Awaiting Review"),
        ("approved", "Approved"), ("rejected", "Rejected"),
        ("superseded", "Superseded"),
    ], default="draft", required=True, tracking=True, copy=False)
    line_ids = fields.One2many("ddfsc.qc.inspection.line", "inspection_id", string="Laboratory Results", copy=True)
    result_state = fields.Selection([("pending", "Pending"), ("pass", "Passed"), ("fail", "Failed")], compute="_compute_result_state", store=True)
    nonconformance_ids = fields.One2many("ddfsc.quality.nonconformance", "inspection_id")
    nonconformance_count = fields.Integer(compute="_compute_nonconformance_count")
    reinspection_reason = fields.Text(copy=False)

    @api.depends("line_ids.result", "line_ids.mandatory")
    def _compute_result_state(self):
        for inspection in self:
            required = inspection.line_ids.filtered("mandatory")
            if not required or any(line.result == "pending" for line in required):
                inspection.result_state = "pending"
            elif any(line.result == "fail" for line in required):
                inspection.result_state = "fail"
            else:
                inspection.result_state = "pass"

    def _compute_nonconformance_count(self):
        for inspection in self:
            inspection.nonconformance_count = len(inspection.nonconformance_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("ddfsc.qc.inspection") or "New"
        return super().create(vals_list)

    @api.model
    def create_for_lot(self, lot):
        plan = lot.quality_plan_id
        if not plan:
            raise UserError(_("No approved QC plan is configured for %s.") % lot.product_id.display_name)
        active = lot.active_qc_inspection_id.filtered(lambda record: record.state not in ("superseded",))
        if active:
            return active
        inspection = self.create({
            "lot_id": lot.id, "plan_id": plan.id,
            "production_id": lot.quality_production_id.id,
            "receipt_id": lot.quality_receipt_id.id,
            "supplier_id": lot.quality_supplier_id.id,
            "line_ids": [(0, 0, line._inspection_line_values()) for line in plan.line_ids],
        })
        lot.active_qc_inspection_id = inspection
        return inspection

    @api.model
    def migrate_legacy_lot_inspections(self):
        """Create immutable inspection documents for pre-refactor lot QC data."""
        lots = self.env["stock.lot"].search([("quality_plan_id", "!=", False), ("active_qc_inspection_id", "=", False)])
        for lot in lots:
            inspection = self.create_for_lot(lot)
            legacy_by_plan_line = {check.plan_line_id.id: check for check in lot.quality_check_ids if check.plan_line_id}
            for line in inspection.line_ids:
                legacy = legacy_by_plan_line.get(line.plan_line_id.id)
                if legacy:
                    line.with_context(ddfsc_legacy_import=True).write({
                        "measured_value": legacy.measured_value, "is_measured": legacy.is_measured,
                        "measured_text": getattr(legacy, "measured_text", False),
                        "entered_by_id": getattr(legacy, "entered_by_id", False).id,
                        "entered_date": getattr(legacy, "entered_date", False),
                    })
            mapping = {"draft": "draft", "submitted": "submitted", "approved": "approved", "rejected": "rejected"}
            if lot.ddfsc_review_state in mapping:
                inspection.write({
                    "state": mapping[lot.ddfsc_review_state], "submitted_by_id": lot.quality_submitted_by_id.id,
                    "submitted_date": lot.quality_submitted_date, "reviewed_by_id": lot.quality_reviewed_by_id.id,
                    "reviewed_date": lot.quality_reviewed_date,
                })
        return len(lots)

    def action_submit(self):
        for inspection in self:
            missing = inspection.line_ids.filtered(lambda line: line.mandatory and line.result == "pending")
            if missing:
                raise UserError(_("Complete all mandatory tests before submission: %s") % ", ".join(missing.mapped("name")))
            inspection.write({"state": "submitted", "submitted_by_id": self.env.user.id, "submitted_date": fields.Datetime.now()})
            inspection._sync_lot_disposition("pending")
            for manager in self.env.ref("ddfsc_quality.group_ddfsc_quality_manager").user_ids:
                inspection.activity_schedule("mail.mail_activity_data_todo", user_id=manager.id, summary=_("QC review required for %s") % inspection.name)
        return True

    def action_review(self):
        if not self.env.user.has_group("ddfsc_quality.group_ddfsc_quality_manager"):
            raise AccessError(_("Only a Quality Manager can approve or reject an inspection."))
        for inspection in self:
            if inspection.state != "submitted":
                raise UserError(_("Submit the inspection before review."))
            approved = inspection.result_state == "pass"
            inspection.write({"state": "approved" if approved else "rejected", "reviewed_by_id": self.env.user.id, "reviewed_date": fields.Datetime.now()})
            inspection._sync_lot_disposition("pass" if approved else "hold")
            if not approved:
                inspection._ensure_nonconformance()
        return True

    def action_start_reinspection(self):
        self.ensure_one()
        if not (self.reinspection_reason or "").strip():
            raise UserError(_("Enter a reinspection reason before starting a new inspection."))
        self.state = "superseded"
        inspection = self.create_for_lot(self.lot_id)
        if inspection == self:
            self.lot_id.active_qc_inspection_id = False
            inspection = self.create_for_lot(self.lot_id)
        inspection.message_post(body=_("Reinspection created from %s. Reason: %s") % (self.name, self.reinspection_reason))
        self.lot_id.write({"ddfsc_quality_state": "pending", "ddfsc_review_state": "draft"})
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "res_id": inspection.id}

    def _sync_lot_disposition(self, quality_state):
        for inspection in self:
            inspection.lot_id.write({
                "ddfsc_quality_state": quality_state,
                "ddfsc_review_state": {"draft": "draft", "submitted": "submitted", "approved": "approved", "rejected": "rejected"}[inspection.state],
                "quality_submitted_by_id": inspection.submitted_by_id.id,
                "quality_submitted_date": inspection.submitted_date,
                "quality_reviewed_by_id": inspection.reviewed_by_id.id,
                "quality_reviewed_date": inspection.reviewed_date,
            })

    def _ensure_nonconformance(self):
        for inspection in self:
            open_ncr = inspection.nonconformance_ids.filtered(lambda ncr: ncr.state not in ("closed", "canceled"))
            if open_ncr:
                continue
            failed = inspection.line_ids.filtered(lambda line: line.mandatory and line.result == "fail")
            self.env["ddfsc.quality.nonconformance"].create({
                "inspection_id": inspection.id, "lot_id": inspection.lot_id.id,
                "affected_qty": sum(inspection.lot_id.quant_ids.filtered(lambda quant: quant.quantity > 0).mapped("quantity")) or 1.0,
                "defect_description": _("Failed mandatory tests: %s") % ", ".join(failed.mapped("name")),
                "production_id": inspection.production_id.id, "picking_id": inspection.receipt_id.id,
                "partner_id": inspection.supplier_id.id,
            })


class DdfscQcInspectionLine(models.Model):
    _name = "ddfsc.qc.inspection.line"
    _description = "DDFSC QC Inspection Result"
    _order = "sequence, id"

    inspection_id = fields.Many2one("ddfsc.qc.inspection", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    plan_line_id = fields.Many2one("ddfsc.quality.plan.line", readonly=True, ondelete="restrict")
    name = fields.Char(required=True, readonly=True)
    mandatory = fields.Boolean(default=True, readonly=True)
    result_type = fields.Selection([( "numeric", "Measured Number"), ("qualitative", "Qualitative Choice")], default="numeric", readonly=True)
    allowed_answers = fields.Char(readonly=True)
    apply_min = fields.Boolean(readonly=True)
    standard_min = fields.Float(readonly=True)
    apply_max = fields.Boolean(readonly=True)
    standard_max = fields.Float(readonly=True)
    note = fields.Char(string="Unit / Method", readonly=True)
    specification = fields.Char(string="Required Range", readonly=True)
    measured_value = fields.Float(string="Measured Result")
    measured_text = fields.Char(string="Observed Result")
    is_measured = fields.Boolean(string="Test Complete", default=False)
    result = fields.Selection([( "pending", "Pending"), ("pass", "Pass"), ("fail", "Fail")], compute="_compute_result", store=True)
    entered_by_id = fields.Many2one("res.users", readonly=True)
    entered_date = fields.Datetime(readonly=True)

    @api.depends("is_measured", "measured_value", "measured_text", "result_type", "allowed_answers", "apply_min", "standard_min", "apply_max", "standard_max")
    def _compute_result(self):
        for line in self:
            if not line.is_measured:
                line.result = "pending"
            elif line.result_type == "qualitative":
                choices = {value.strip().casefold() for value in (line.allowed_answers or "").split(",") if value.strip()}
                line.result = "pass" if (line.measured_text or "").strip().casefold() in choices else "fail"
            else:
                line.result = "pass" if (not line.apply_min or line.measured_value >= line.standard_min) and (not line.apply_max or line.measured_value <= line.standard_max) else "fail"

    @api.onchange("measured_value", "measured_text")
    def _onchange_measurement(self):
        self.is_measured = True

    def write(self, values):
        if {"measured_value", "measured_text", "is_measured"}.intersection(values):
            locked = self.mapped("inspection_id").filtered(lambda inspection: inspection.state != "draft")
            if locked and not self.env.context.get("ddfsc_legacy_import"):
                raise UserError(_("Submitted or reviewed inspection results are locked. Start a reinspection instead."))
            values = dict(values, entered_by_id=self.env.user.id, entered_date=fields.Datetime.now())
        return super().write(values)


class DdfscQualityPlanLine(models.Model):
    _inherit = "ddfsc.quality.plan.line"

    def _inspection_line_values(self):
        self.ensure_one()
        return {
            "sequence": self.sequence, "plan_line_id": self.id, "name": dict(self._fields["check_type"].selection).get(self.check_type),
            "mandatory": self.mandatory, "result_type": self.result_type, "allowed_answers": self.allowed_answers,
            "apply_min": self.apply_min, "standard_min": self.standard_min, "apply_max": self.apply_max,
            "standard_max": self.standard_max, "note": self.note, "specification": self.specification,
        }


class StockLot(models.Model):
    _inherit = "stock.lot"

    qc_inspection_ids = fields.One2many("ddfsc.qc.inspection", "lot_id", string="QC Inspections")
    active_qc_inspection_id = fields.Many2one("ddfsc.qc.inspection", string="Active QC Inspection", copy=False)

    def action_prepare_quality_checks(self):
        return self._ensure_qc_inspection()

    def _ensure_qc_inspection(self):
        for lot in self:
            if lot.quality_plan_id and not lot.active_qc_inspection_id:
                self.env["ddfsc.qc.inspection"].create_for_lot(lot)
        return True

    def action_open_qc_inspection(self):
        self.ensure_one()
        self._ensure_qc_inspection()
        if not self.active_qc_inspection_id:
            raise UserError(_("This lot does not require a QC inspection because no approved plan applies."))
        return {"type": "ir.actions.act_window", "name": _("QC Inspection"), "res_model": "ddfsc.qc.inspection", "view_mode": "form", "res_id": self.active_qc_inspection_id.id}

    def action_submit_quality(self):
        self._ensure_qc_inspection()
        return self.mapped("active_qc_inspection_id").action_submit()

    def action_approve_quality(self):
        self._ensure_qc_inspection()
        return self.mapped("active_qc_inspection_id").action_review()

    def action_request_reinspection(self):
        self._ensure_qc_inspection()
        for lot in self:
            inspection = lot.active_qc_inspection_id
            inspection.reinspection_reason = lot.correction_reason
            inspection.action_start_reinspection()
        return True
