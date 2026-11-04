from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DdfscOvertimePolicy(models.Model):
    _name = "ddfsc.overtime.policy"
    _description = "Overtime Eligibility Policy"
    _order = "date_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date()
    minimum_minutes = fields.Integer(required=True, default=30)
    include_non_working_days = fields.Boolean(
        string="Treat work on a non-working day as overtime", default=True,
        help="When disabled, attendance on a rest day or public holiday is not proposed as overtime.",
    )
    active = fields.Boolean(default=True)
    note = fields.Text(help="Record the approved policy here. Payroll rates are configured separately.")

    @api.constrains("minimum_minutes", "date_from", "date_to")
    def _check_values(self):
        for record in self:
            if record.minimum_minutes < 0:
                raise ValidationError(_("Minimum overtime minutes cannot be negative."))
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(_("Policy end date cannot be before its effective date."))

    @api.model
    def policy_for(self, company, work_date):
        policy = self.search([
            ("company_id", "=", company.id), ("active", "=", True),
            ("date_from", "<=", work_date), "|", ("date_to", "=", False), ("date_to", ">=", work_date),
        ], order="date_from desc", limit=1)
        if not policy:
            raise UserError(_("Create an active overtime policy for %s before generating overtime candidates.") % work_date)
        return policy


class DdfscOvertimeRequest(models.Model):
    _name = "ddfsc.overtime.request"
    _description = "Overtime Review"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "work_date desc, employee_id"

    name = fields.Char(compute="_compute_name", store=True)
    employee_id = fields.Many2one("hr.employee", required=True, readonly=True, index=True)
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    work_date = fields.Date(required=True, readonly=True, index=True)
    policy_id = fields.Many2one("ddfsc.overtime.policy", required=True, readonly=True)
    attendance_ids = fields.Many2many("hr.attendance", string="Source Attendance", readonly=True)
    scheduled_start = fields.Datetime(readonly=True)
    scheduled_end = fields.Datetime(readonly=True)
    first_check_in = fields.Datetime(readonly=True)
    last_check_out = fields.Datetime(readonly=True)
    eligible_hours = fields.Float(readonly=True, digits=(16, 2), tracking=True)
    approved_hours = fields.Float(digits=(16, 2), tracking=True)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Pending Approval"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="draft", required=True, tracking=True, index=True,
    )
    requested_by = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    reviewed_by = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    review_note = fields.Text(tracking=True)

    _employee_day_unique = models.Constraint(
        "unique(employee_id, work_date)", "Only one overtime review may exist per employee and work date."
    )

    @api.depends("employee_id", "work_date")
    def _compute_name(self):
        for record in self:
            record.name = _("Overtime: %(employee)s — %(date)s", employee=record.employee_id.name or "", date=record.work_date or "")

    @api.constrains("approved_hours", "eligible_hours")
    def _check_approved_hours(self):
        for record in self:
            if record.approved_hours < 0 or record.approved_hours > record.eligible_hours:
                raise ValidationError(_("Approved hours must be between zero and the eligible overtime hours."))

    def action_submit(self):
        for record in self.filtered(lambda item: item.state == "draft"):
            if not record.eligible_hours:
                raise UserError(_("There are no eligible overtime hours to submit."))
            record.approved_hours = record.eligible_hours
            record.state = "submitted"

    def action_approve(self):
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise UserError(_("Only an Attendance Administrator can approve overtime."))
        for record in self.filtered(lambda item: item.state == "submitted"):
            if not record.approved_hours:
                raise UserError(_("Enter approved hours before approval."))
            record.write({"state": "approved", "reviewed_by": self.env.user.id, "reviewed_at": fields.Datetime.now()})

    def action_reject(self):
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise UserError(_("Only an Attendance Administrator can reject overtime."))
        self.filtered(lambda item: item.state == "submitted").write({
            "state": "rejected", "reviewed_by": self.env.user.id, "reviewed_at": fields.Datetime.now(),
        })

    def action_reset_to_draft(self):
        self.filtered(lambda item: item.state in ("submitted", "rejected")).write({"state": "draft"})

    @api.model
    def generate_candidates(self, work_date=None):
        work_date = work_date or (fields.Date.context_today(self) - timedelta(days=1))
        if work_date >= fields.Date.context_today(self):
            return self.browse()
        day_start = datetime.combine(work_date, time.min)
        day_end = day_start + timedelta(days=1)
        Attendance = self.env["hr.attendance"]
        Leave = self.env["hr.leave"]
        candidates = self.browse()
        employees = self.env["hr.employee"].search([("active", "=", True)])
        for employee in employees:
            attendances = Attendance.search([
                ("employee_id", "=", employee.id), ("check_in", ">=", day_start),
                ("check_in", "<", day_end), ("check_out", "!=", False),
            ], order="check_in")
            if not attendances:
                continue
            # Leave conflicts must be resolved before overtime is considered.
            if Leave.search_count([
                ("employee_id", "=", employee.id), ("state", "=", "validate"),
                ("date_from", "<=", day_end), ("date_to", ">=", day_start),
            ]):
                continue
            policy = self.env["ddfsc.overtime.policy"].policy_for(employee.company_id, work_date)
            scheduled_start, scheduled_end, _assignment = self.env["ddfsc.attendance.exception"]._scheduled_window(employee, work_date)
            first_check_in = min(attendances.mapped("check_in"))
            last_check_out = max(attendances.mapped("check_out"))
            if scheduled_start:
                eligible_seconds = max((scheduled_start - first_check_in).total_seconds(), 0) + max((last_check_out - scheduled_end).total_seconds(), 0)
            elif policy.include_non_working_days:
                eligible_seconds = sum((item.check_out - item.check_in).total_seconds() for item in attendances)
            else:
                continue
            eligible_hours = round(eligible_seconds / 3600, 2)
            if eligible_hours * 60 < policy.minimum_minutes:
                continue
            existing = self.search([("employee_id", "=", employee.id), ("work_date", "=", work_date)], limit=1)
            values = {
                "policy_id": policy.id, "attendance_ids": [(6, 0, attendances.ids)],
                "scheduled_start": scheduled_start, "scheduled_end": scheduled_end,
                "first_check_in": first_check_in, "last_check_out": last_check_out,
                "eligible_hours": eligible_hours,
            }
            if existing:
                if existing.state == "draft":
                    existing.write(values)
                candidates |= existing
            else:
                candidates |= self.create(dict(values, employee_id=employee.id, work_date=work_date))
        return candidates

    def action_generate_yesterday(self):
        candidates = self.generate_candidates()
        return {
            "type": "ir.actions.act_window", "name": _("Overtime Candidates"),
            "res_model": self._name, "view_mode": "list,form", "domain": [("id", "in", candidates.ids)],
        }
