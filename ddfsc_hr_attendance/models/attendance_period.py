from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DdfscAttendancePeriod(models.Model):
    _name = "ddfsc.attendance.period"
    _description = "Attendance Validation Period"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_to desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    state = fields.Selection(
        [("draft", "Draft"), ("validated", "Validated"), ("locked", "Locked"), ("reopened", "Reopened")],
        required=True, default="draft", tracking=True, index=True,
    )
    validated_by = fields.Many2one("res.users", readonly=True)
    validated_at = fields.Datetime(readonly=True)
    locked_by = fields.Many2one("res.users", readonly=True)
    locked_at = fields.Datetime(readonly=True)
    reopen_reason = fields.Text(tracking=True)
    reopened_by = fields.Many2one("res.users", readonly=True)
    reopened_at = fields.Datetime(readonly=True)
    attendance_count = fields.Integer(compute="_compute_review_counts")
    open_exception_count = fields.Integer(compute="_compute_review_counts")
    pending_overtime_count = fields.Integer(compute="_compute_review_counts")

    @api.depends("company_id", "date_from", "date_to")
    def _compute_name(self):
        for record in self:
            record.name = _("Attendance: %(from)s – %(to)s", **{"from": record.date_from or "", "to": record.date_to or ""})

    @api.depends("company_id", "date_from", "date_to")
    def _compute_review_counts(self):
        Attendance = self.env["hr.attendance"]
        Exception = self.env["ddfsc.attendance.exception"]
        Overtime = self.env["ddfsc.overtime.request"]
        for record in self:
            if not record.date_from or not record.date_to:
                record.attendance_count = record.open_exception_count = record.pending_overtime_count = 0
                continue
            employees = self.env["hr.employee"].search([("company_id", "=", record.company_id.id)])
            record.attendance_count = Attendance.search_count([
                ("employee_id", "in", employees.ids), ("date", ">=", record.date_from), ("date", "<=", record.date_to),
            ])
            record.open_exception_count = Exception.search_count([
                ("company_id", "=", record.company_id.id), ("state", "=", "open"),
                ("scheduled_date", ">=", record.date_from), ("scheduled_date", "<=", record.date_to),
            ])
            record.pending_overtime_count = Overtime.search_count([
                ("company_id", "=", record.company_id.id), ("work_date", ">=", record.date_from), ("work_date", "<=", record.date_to),
                ("state", "in", ("draft", "submitted")),
            ])

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for record in self:
            if record.date_to < record.date_from:
                raise ValidationError(_("Period end date cannot be before the start date."))

    @api.constrains("company_id", "date_from", "date_to", "state")
    def _check_overlap(self):
        for record in self.filtered(lambda item: item.state != "draft"):
            if self.search_count([
                ("id", "!=", record.id), ("company_id", "=", record.company_id.id),
                ("state", "in", ("validated", "locked", "reopened")),
                ("date_from", "<=", record.date_to), ("date_to", ">=", record.date_from),
            ]):
                raise ValidationError(_("Attendance validation periods for the same company cannot overlap."))

    def _require_attendance_manager(self):
        if not self.env.is_superuser() and not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise UserError(_("Only an Attendance Administrator can validate or lock attendance periods."))

    def action_validate(self):
        self._require_attendance_manager()
        for record in self.filtered(lambda item: item.state in ("draft", "reopened")):
            record._compute_review_counts()
            if record.open_exception_count:
                raise UserError(_("Resolve or explicitly ignore the %(count)s open attendance exception(s) before validation.", count=record.open_exception_count))
            if record.pending_overtime_count:
                raise UserError(_("Approve or reject the %(count)s pending overtime review(s) before validation.", count=record.pending_overtime_count))
            record.write({"state": "validated", "validated_by": self.env.user.id, "validated_at": fields.Datetime.now()})

    def action_lock(self):
        self._require_attendance_manager()
        self.filtered(lambda item: item.state == "validated").write({
            "state": "locked", "locked_by": self.env.user.id, "locked_at": fields.Datetime.now(),
        })

    def action_reopen(self):
        self._require_attendance_manager()
        for record in self.filtered(lambda item: item.state == "locked"):
            if not record.reopen_reason:
                raise UserError(_("Enter the controlled reopening reason before reopening this period."))
            record.write({"state": "reopened", "reopened_by": self.env.user.id, "reopened_at": fields.Datetime.now()})

    @api.model
    def is_locked_for(self, employee, attendance_date):
        if not employee or not attendance_date:
            return False
        return bool(self.search_count([
            ("company_id", "=", employee.company_id.id), ("state", "=", "locked"),
            ("date_from", "<=", attendance_date), ("date_to", ">=", attendance_date),
        ]))
