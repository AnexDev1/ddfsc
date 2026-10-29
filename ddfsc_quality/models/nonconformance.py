from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DdfscQualityNonconformance(models.Model):
    _name = "ddfsc.quality.nonconformance"
    _description = "Quality Non-Conformance"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    lot_id = fields.Many2one("stock.lot", required=True, index=True, ondelete="restrict", tracking=True)
    inspection_id = fields.Many2one("ddfsc.qc.inspection", string="QC Inspection", ondelete="restrict", tracking=True)
    product_id = fields.Many2one(related="lot_id.product_id", store=True)
    production_id = fields.Many2one("mrp.production", tracking=True)
    picking_id = fields.Many2one("stock.picking", string="Receipt / Transfer", tracking=True)
    partner_id = fields.Many2one("res.partner", string="Supplier", tracking=True)
    affected_qty = fields.Float(string="Affected Quantity", required=True, tracking=True)
    severity = fields.Selection(
        [("minor", "Minor"), ("major", "Major"), ("critical", "Critical")],
        default="major", required=True, tracking=True,
    )
    defect_description = fields.Text(required=True, tracking=True)
    owner_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, tracking=True)
    due_date = fields.Date(tracking=True)
    state = fields.Selection(
        [("new", "New"), ("investigation", "Under Investigation"),
         ("action", "Action Required"), ("verification", "Pending Verification"),
         ("closed", "Closed"), ("canceled", "Canceled")],
        default="new", required=True, tracking=True,
    )
    disposition = fields.Selection(
        [("return", "Return to Supplier"), ("rework", "Rework"), ("scrap", "Scrap"),
         ("retest", "Additional Test / Reinspection"), ("exception", "Release by Exception"),
         ("other", "Other")], tracking=True,
    )
    root_cause = fields.Text(tracking=True)
    corrective_action = fields.Text(tracking=True)
    preventive_action = fields.Text(tracking=True)
    verification = fields.Text(tracking=True)
    closure_note = fields.Text(tracking=True)
    closed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    closed_date = fields.Datetime(readonly=True, copy=False)
    active = fields.Boolean(default=True)

    @api.depends("due_date", "state")
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for record in self:
            record.is_overdue = bool(
                record.due_date and record.due_date < today
                and record.state not in ("closed", "canceled")
            )

    is_overdue = fields.Boolean(compute="_compute_is_overdue", search="_search_is_overdue")

    def _search_is_overdue(self, operator, value):
        domain = [
            ("due_date", "<", fields.Date.today()),
            ("state", "not in", ("closed", "canceled")),
        ]
        if (operator == "=" and value) or (operator == "!=" and not value):
            return domain
        return [
            "|", "|",
            ("due_date", "=", False),
            ("due_date", ">=", fields.Date.today()),
            ("state", "in", ("closed", "canceled")),
        ]

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            if values.get("name", "New") == "New":
                values["name"] = self.env["ir.sequence"].next_by_code("ddfsc.quality.nonconformance") or "New"
            lot = self.env["stock.lot"].browse(values.get("lot_id")).exists()
            if lot:
                lines = self.env["stock.move.line"].search([("lot_id", "=", lot.id)], order="date desc, id desc")
                productions = lines.move_id.production_id | lines.move_id.raw_material_production_id
                production = productions[:1]
                receipt = lines.picking_id.filtered(lambda picking: picking.picking_type_code == "incoming")[:1]
                values.setdefault("production_id", production.id)
                values.setdefault("picking_id", receipt.id)
                values.setdefault("partner_id", receipt.partner_id.id)
        records = super().create(values_list)
        for record in records:
            record.message_post(body=_("Non-conformance opened for lot %s.") % record.lot_id.display_name)
            if record.due_date:
                record.activity_schedule(
                    "mail.mail_activity_data_todo", user_id=record.owner_id.id,
                    date_deadline=record.due_date,
                    summary=_("Investigate non-conformance %s") % record.name,
                )
        return records

    def write(self, values):
        result = super().write(values)
        if {"owner_id", "due_date"}.intersection(values):
            self._sync_investigation_activity()
        return result

    def _sync_investigation_activity(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        for record in self.filtered(lambda item: item.state not in ("closed", "canceled")):
            summary = _("Investigate non-conformance %s") % record.name
            activities = record.activity_ids.filtered(
                lambda activity: activity.activity_type_id == activity_type
                and activity.summary == summary
            )
            if not record.due_date:
                continue
            if activities:
                activities.write({
                    "user_id": record.owner_id.id,
                    "date_deadline": record.due_date,
                })
            else:
                record.activity_schedule(
                    "mail.mail_activity_data_todo", user_id=record.owner_id.id,
                    date_deadline=record.due_date, summary=summary,
                )

    @api.model
    def _cron_notify_overdue(self):
        overdue = self.search([
            ("due_date", "<", fields.Date.today()),
            ("state", "not in", ("closed", "canceled")),
        ])
        overdue._sync_investigation_activity()
        for record in overdue:
            summary = _("Overdue non-conformance %s") % record.name
            managers = self.env.ref("ddfsc_quality.group_ddfsc_quality_manager").user_ids
            for manager in managers:
                if not record.activity_ids.filtered(
                    lambda activity: activity.user_id == manager and activity.summary == summary
                ):
                    self.env["mail.activity"].create({
                        "res_model_id": self.env["ir.model"]._get_id(self._name),
                        "res_id": record.id,
                        "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                        "user_id": manager.id,
                        "date_deadline": fields.Date.today(),
                        "summary": summary,
                        "note": _("The corrective action due date has passed."),
                    })
        return True

    @api.constrains("affected_qty")
    def _check_affected_qty(self):
        if self.filtered(lambda record: record.affected_qty <= 0):
            raise ValidationError(_("Affected quantity must be greater than zero."))

    def action_investigate(self):
        self.write({"state": "investigation"})

    def action_require_action(self):
        if self.filtered(lambda record: not record.root_cause):
            raise UserError(_("Record the root cause before assigning corrective action."))
        self.write({"state": "action"})

    def action_verify(self):
        if self.filtered(lambda record: not record.corrective_action):
            raise UserError(_("Record the corrective action before verification."))
        self.write({"state": "verification"})

    def action_close(self):
        if not self.env.user.has_group("ddfsc_quality.group_ddfsc_quality_manager"):
            raise AccessError(_("Only a Quality Manager can close a non-conformance."))
        for record in self:
            if not record.disposition or not record.verification or not record.closure_note:
                raise UserError(_("Disposition, verification, and closure note are required before closure."))
            record.write({"state": "closed", "closed_by_id": self.env.user.id, "closed_date": fields.Datetime.now()})
            summary = _("Investigate non-conformance %s") % record.name
            record.activity_ids.filtered(lambda activity: activity.summary == summary).action_done()
        return True

    def action_reinspect(self):
        self.ensure_one()
        if self.inspection_id:
            self.inspection_id.reinspection_reason = _("Reinspection requested from %s") % self.name
            return self.inspection_id.action_start_reinspection()
        self.lot_id.correction_reason = _("Reinspection requested from %s") % self.name
        self.lot_id.action_request_reinspection()
        return {"type": "ir.actions.act_window", "res_model": "stock.lot", "view_mode": "form", "res_id": self.lot_id.id}


class StockLot(models.Model):
    _inherit = "stock.lot"

    nonconformance_ids = fields.One2many("ddfsc.quality.nonconformance", "lot_id")
    nonconformance_count = fields.Integer(compute="_compute_nonconformance_count")

    def _compute_nonconformance_count(self):
        for lot in self:
            lot.nonconformance_count = len(lot.nonconformance_ids)

    def _ensure_nonconformance(self):
        Nonconformance = self.env["ddfsc.quality.nonconformance"]
        for lot in self:
            existing = Nonconformance.search_count([("lot_id", "=", lot.id), ("state", "not in", ("closed", "canceled"))])
            if existing:
                continue
            failed = lot.quality_check_ids.filtered(lambda check: check.mandatory and check.result == "fail")
            description = ", ".join(failed.mapped("check_type")) or _("Manual quality hold")
            qty = sum(lot.quant_ids.filtered(lambda quant: quant.quantity > 0).mapped("quantity")) or 1.0
            Nonconformance.create({
                "lot_id": lot.id,
                "affected_qty": qty,
                "defect_description": _("Failed mandatory tests: %s") % description,
                "production_id": failed[:1].production_id.id,
            })

    def action_quality_reject(self):
        result = super().action_quality_reject()
        self._ensure_nonconformance()
        return result
