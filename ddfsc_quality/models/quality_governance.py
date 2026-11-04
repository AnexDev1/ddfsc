from odoo import _, Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


def _next_version(version):
    """Return a predictable next version while accepting existing free-form values."""
    try:
        major, minor = (str(version or "1.0").split(".", 1) + ["0"])[:2]
        return "%s.%s" % (int(major), int(minor) + 1)
    except (TypeError, ValueError):
        return _("Next")


class DdfscQualityPlan(models.Model):
    _name = "ddfsc.quality.plan"
    _inherit = ["ddfsc.quality.plan", "mail.thread"]

    version = fields.Char(default="1.0", required=True, tracking=True)
    effective_from = fields.Date(string="Effective From", tracking=True)
    effective_to = fields.Date(string="Effective Until", tracking=True)
    approval_state = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("retired", "Retired")],
        default="draft",
        required=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)

    @api.constrains("effective_from", "effective_to")
    def _check_effective_dates(self):
        for plan in self:
            if plan.effective_from and plan.effective_to and plan.effective_to < plan.effective_from:
                raise ValidationError(_("Effective Until cannot be before Effective From."))

    def write(self, values):
        governed = {"checkpoint", "product_ids", "line_ids", "version", "effective_from", "effective_to"}
        if governed.intersection(values) and self.filtered(lambda plan: plan.approval_state == "approved") and not self.env.context.get("quality_plan_transition"):
            raise UserError(_("An approved QC plan is locked. Create a new version instead."))
        return super().write(values)

    def action_approve(self):
        if not self.env.user.has_group("ddfsc_quality.group_ddfsc_quality_manager"):
            raise AccessError(_("Only a Quality Manager can approve a QC plan."))
        for plan in self:
            if not plan.line_ids:
                raise UserError(_("Add at least one test before approving this plan."))
            if not plan.product_ids:
                raise UserError(_("Select at least one product before approving this plan."))
            if plan.demo_specification:
                raise UserError(_(
                    "This plan still contains demonstration limits. Clear 'Demo Specification' "
                    "only after the factory Quality Manager confirms every test and limit."
                ))
            effective_from = plan.effective_from or fields.Date.today()
            overlap_domain = [
                ("id", "!=", plan.id),
                ("approval_state", "=", "approved"),
                ("active", "=", True),
                ("checkpoint", "=", plan.checkpoint),
                ("product_ids", "in", plan.product_ids.ids),
                "|", ("effective_to", "=", False), ("effective_to", ">=", effective_from),
            ]
            if plan.effective_to:
                overlap_domain += [
                    "|", ("effective_from", "=", False),
                    ("effective_from", "<=", plan.effective_to),
                ]
            overlapping = self.search(overlap_domain)
            if overlapping:
                raise UserError(_(
                    "An approved plan already covers one or more of these products: %s. "
                    "Retire that plan, or end its effective period before approving this version."
                ) % ", ".join(overlapping.mapped("display_name")))
            plan.write({
                "approval_state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_date": fields.Datetime.now(),
                "effective_from": effective_from,
            })
        return True

    def action_new_version(self):
        self.ensure_one()
        copied_lines = []
        for line in self.line_ids:
            values = line.copy_data()[0]
            values.pop("plan_id", None)
            copied_lines.append(Command.create(values))
        copy = self.copy({
            "name": _("%s (New Version)") % self.name,
            "version": _next_version(self.version),
            "approval_state": "draft",
            "approved_by_id": False,
            "approved_date": False,
            "effective_from": False,
            "effective_to": False,
            "line_ids": copied_lines,
        })
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "res_id": copy.id}

    def action_retire(self):
        today = fields.Date.today()
        for plan in self:
            end_date = max(today, plan.effective_from or today)
            plan.with_context(quality_plan_transition=True).write({
                "approval_state": "retired", "active": False,
                "effective_to": end_date,
            })
        return True


class DdfscQualityPlanLine(models.Model):
    _inherit = "ddfsc.quality.plan.line"

    mandatory = fields.Boolean(default=True)
    result_type = fields.Selection(
        [("numeric", "Measured Number"), ("qualitative", "Qualitative Choice")],
        default="numeric",
        required=True,
    )
    allowed_answers = fields.Char(
        help="Comma-separated acceptable answers, for example: Pass, Intact, Acceptable."
    )

    @api.constrains("result_type", "allowed_answers", "apply_min", "apply_max")
    def _check_result_rule(self):
        for line in self:
            if line.result_type == "qualitative" and not line.allowed_answers:
                raise ValidationError(_("Enter at least one acceptable answer for a qualitative test."))

    def write(self, values):
        if self.filtered(lambda line: line.plan_id.approval_state == "approved"):
            raise UserError(_("Tests on an approved QC plan are locked. Create a new plan version."))
        return super().write(values)

    def unlink(self):
        if self.filtered(lambda line: line.plan_id.approval_state == "approved"):
            raise UserError(_("Tests on an approved QC plan cannot be deleted."))
        return super().unlink()


class DdfscQualityCheck(models.Model):
    _inherit = "ddfsc.quality.check"

    mandatory = fields.Boolean(related="plan_line_id.mandatory", store=True)
    result_type = fields.Selection(related="plan_line_id.result_type", store=True)
    allowed_answers = fields.Char(related="plan_line_id.allowed_answers", store=True)
    measured_text = fields.Char(string="Observed Result")
    entered_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    entered_date = fields.Datetime(readonly=True, copy=False)
    review_state = fields.Selection(related="lot_id.ddfsc_review_state")

    @api.onchange("measured_text")
    def _onchange_measured_text(self):
        self.filtered(lambda check: check.result_type == "qualitative").is_measured = True

    @api.depends(
        "is_measured", "measured_value", "measured_text", "result_type", "allowed_answers",
        "apply_min", "standard_min", "apply_max", "standard_max",
    )
    def _compute_result(self):
        qualitative = self.filtered(lambda check: check.result_type == "qualitative")
        numeric = self - qualitative
        for check in numeric:
            if not check.is_measured:
                check.result = "pending"
                continue
            ok = not check.apply_min or check.measured_value >= check.standard_min
            ok = ok and (not check.apply_max or check.measured_value <= check.standard_max)
            check.result = "pass" if ok else "fail"
        for check in qualitative:
            if not check.is_measured or not (check.measured_text or "").strip():
                check.result = "pending"
                continue
            accepted = {value.strip().casefold() for value in (check.allowed_answers or "").split(",") if value.strip()}
            check.result = "pass" if check.measured_text.strip().casefold() in accepted else "fail"

    def write(self, values):
        result_fields = {"measured_value", "measured_text", "is_measured"}
        if result_fields.intersection(values):
            locked = self.filtered(lambda check: check.lot_id.ddfsc_review_state in ("submitted", "approved", "rejected"))
            if locked and not self.env.context.get("ddfsc_quality_correction"):
                raise UserError(_("Submitted QC results are locked. Request a correction or reinspection first."))
            values = dict(values, entered_by_id=self.env.user.id, entered_date=fields.Datetime.now())
        return super().write(values)


class StockLot(models.Model):
    _inherit = "stock.lot"

    ddfsc_review_state = fields.Selection(
        [("draft", "Data Entry"), ("submitted", "Awaiting Review"),
         ("approved", "Approved"), ("rejected", "Rejected")],
        default="draft",
        required=True,
        string="Inspection Status",
        tracking=True,
        copy=False,
    )
    quality_submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    quality_submitted_date = fields.Datetime(readonly=True, copy=False)
    quality_reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    quality_reviewed_date = fields.Datetime(readonly=True, copy=False)
    correction_reason = fields.Text(copy=False)
    quality_revision_ids = fields.One2many("ddfsc.quality.revision", "lot_id", string="Inspection History")
    quality_revision_count = fields.Integer(compute="_compute_quality_revision_count")
    quality_receipt_id = fields.Many2one(
        "stock.picking", string="Source Receipt", compute="_compute_quality_sources",
        search="_search_quality_receipt",
    )
    quality_supplier_id = fields.Many2one(
        "res.partner", string="Supplier", compute="_compute_quality_sources",
        search="_search_quality_supplier",
    )
    quality_production_id = fields.Many2one(
        "mrp.production", string="Manufacturing Order", compute="_compute_quality_sources",
        search="_search_quality_production",
    )

    @api.depends("quant_ids", "product_id")
    def _compute_quality_sources(self):
        MoveLine = self.env["stock.move.line"]
        for lot in self:
            lines = MoveLine.search([("lot_id", "=", lot.id)], order="date desc, id desc")
            receipt = lines.picking_id.filtered(
                lambda picking: picking.picking_type_code == "incoming"
            )[:1]
            productions = lines.move_id.production_id | lines.move_id.raw_material_production_id
            lot.quality_receipt_id = receipt
            lot.quality_supplier_id = receipt.partner_id
            lot.quality_production_id = productions[:1]

    def _search_quality_receipt(self, operator, value):
        pickings = self.env["stock.picking"].search([
            ("id", operator, value), ("picking_type_code", "=", "incoming")
        ])
        lines = self.env["stock.move.line"].search([("picking_id", "in", pickings.ids)])
        return [("id", "in", lines.lot_id.ids)]

    def _search_quality_supplier(self, operator, value):
        pickings = self.env["stock.picking"].search([
            ("partner_id", operator, value), ("picking_type_code", "=", "incoming")
        ])
        lines = self.env["stock.move.line"].search([("picking_id", "in", pickings.ids)])
        return [("id", "in", lines.lot_id.ids)]

    def _search_quality_production(self, operator, value):
        moves = self.env["stock.move"].search([
            "|", ("production_id", operator, value),
            ("raw_material_production_id", operator, value),
        ])
        lines = self.env["stock.move.line"].search([("move_id", "in", moves.ids)])
        return [("id", "in", lines.lot_id.ids)]

    def _compute_quality_revision_count(self):
        for lot in self:
            lot.quality_revision_count = len(lot.quality_revision_ids)

    def action_submit_quality(self):
        for lot in self:
            required = lot.quality_check_ids.filtered("mandatory")
            missing = required.filtered(lambda check: not check.is_measured)
            if missing:
                labels = dict(missing._fields["check_type"].selection)
                names = [labels.get(check.check_type, check.check_type) for check in missing]
                raise UserError(_("Complete all mandatory tests before submission: %s") % ", ".join(names))
            lot.write({"ddfsc_review_state": "submitted", "quality_submitted_by_id": self.env.user.id,
                       "quality_submitted_date": fields.Datetime.now()})
            managers = self.env.ref("ddfsc_quality.group_ddfsc_quality_manager").user_ids
            for manager in managers:
                lot.activity_schedule("mail.mail_activity_data_todo", user_id=manager.id,
                                      summary=_("QC review required for lot %s") % lot.name)
        return True

    def action_approve_quality(self):
        if not self.env.user.has_group("ddfsc_quality.group_ddfsc_quality_manager"):
            raise AccessError(_("Only a Quality Manager can approve an inspection."))
        for lot in self:
            if lot.ddfsc_review_state != "submitted":
                raise UserError(_("Submit the inspection before approval."))
            failed = lot.quality_check_ids.filtered(lambda check: check.mandatory and check.result == "fail")
            lot.write({"ddfsc_review_state": "rejected" if failed else "approved",
                       "ddfsc_quality_state": "hold" if failed else "pass",
                       "quality_reviewed_by_id": self.env.user.id,
                       "quality_reviewed_date": fields.Datetime.now()})
            prefix = _("QC review required for lot %s") % lot.name
            lot.activity_ids.filtered(
                lambda activity: activity.activity_type_id == self.env.ref("mail.mail_activity_data_todo")
                and activity.summary == prefix
            ).action_done()
            if failed:
                lot._ensure_nonconformance()
                managers = self.env.ref("ddfsc_quality.group_ddfsc_quality_manager").user_ids - self.env.user
                for manager in managers:
                    lot.activity_schedule("mail.mail_activity_data_todo", user_id=manager.id,
                                          summary=_("QC failure on lot %s") % lot.name,
                                          note=_("Review the generated non-conformance and disposition."))
        return True

    def _snapshot_quality(self, reason):
        for lot in self:
            revision = self.env["ddfsc.quality.revision"].create({
                "lot_id": lot.id, "reason": reason, "review_state": lot.ddfsc_review_state,
                "quality_state": lot.ddfsc_quality_state, "reviewed_by_id": lot.quality_reviewed_by_id.id,
                "reviewed_date": lot.quality_reviewed_date,
            })
            for check in lot.quality_check_ids:
                self.env["ddfsc.quality.revision.line"].create({
                    "revision_id": revision.id, "check_type": check.check_type,
                    "specification": check.specification, "measured_value": check.measured_value,
                    "measured_text": check.measured_text, "result": check.result,
                })

    def action_request_reinspection(self):
        for lot in self:
            if not (lot.correction_reason or "").strip():
                raise UserError(_("Enter a correction or reinspection reason first."))
            lot._snapshot_quality(lot.correction_reason)
            lot.quality_check_ids.with_context(ddfsc_quality_correction=True).write({
                "measured_value": 0.0, "measured_text": False, "is_measured": False,
                "entered_by_id": False, "entered_date": False,
            })
            lot.write({"ddfsc_review_state": "draft", "ddfsc_quality_state": "pending",
                       "quality_submitted_by_id": False, "quality_submitted_date": False,
                       "quality_reviewed_by_id": False, "quality_reviewed_date": False,
                       "correction_reason": False})
        return True

    def _ddfsc_apply_quality_checks(self):
        result = super()._ddfsc_apply_quality_checks()
        for lot in self.filtered(lambda item: item.ddfsc_review_state not in ("approved", "rejected")):
            if lot.ddfsc_quality_state == "pass":
                lot.ddfsc_quality_state = "pending"
        return result

    def _notify_quality_managers(self, summary, note=False):
        managers = self.env.ref("ddfsc_quality.group_ddfsc_quality_manager").user_ids
        for lot in self:
            for manager in managers:
                duplicate = lot.activity_ids.filtered(
                    lambda activity: activity.user_id == manager and activity.summary == summary
                )
                if not duplicate:
                    lot.activity_schedule(
                        "mail.mail_activity_data_todo", user_id=manager.id,
                        summary=summary, note=note or False,
                    )

    def action_quality_hold(self):
        result = super().action_quality_hold()
        for lot in self:
            lot._notify_quality_managers(
                _("QC hold requires review for lot %s") % lot.name,
                lot.quality_release_note or _("Review the lot and record a disposition."),
            )
        return result

    def action_quality_reject(self):
        result = super().action_quality_reject()
        for lot in self:
            lot._notify_quality_managers(
                _("Rejected QC lot %s requires disposition") % lot.name,
                lot.quality_release_note,
            )
        return result

    def action_quality_release(self):
        result = super().action_quality_release()
        for lot in self:
            lot.message_post(body=_(
                "Released by quality exception by %(user)s. Reason: %(reason)s",
                user=self.env.user.display_name,
                reason=lot.quality_release_note,
            ))
        return result


class DdfscQualityRevision(models.Model):
    _name = "ddfsc.quality.revision"
    _description = "Archived QC Inspection"
    _order = "create_date desc, id desc"

    lot_id = fields.Many2one("stock.lot", required=True, ondelete="cascade")
    reason = fields.Text(required=True)
    review_state = fields.Char(readonly=True)
    quality_state = fields.Char(readonly=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_date = fields.Datetime(readonly=True)
    line_ids = fields.One2many("ddfsc.quality.revision.line", "revision_id", readonly=True)


class DdfscQualityRevisionLine(models.Model):
    _name = "ddfsc.quality.revision.line"
    _description = "Archived QC Result"

    revision_id = fields.Many2one("ddfsc.quality.revision", required=True, ondelete="cascade")
    check_type = fields.Char(readonly=True)
    specification = fields.Char(readonly=True)
    measured_value = fields.Float(readonly=True)
    measured_text = fields.Char(readonly=True)
    result = fields.Char(readonly=True)
