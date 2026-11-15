from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    source = fields.Selection(
        [("manual", "Manual"), ("biometric", "Biometric"), ("import", "Imported")],
        default="manual",
        required=True,
        tracking=True,
    )
    check_in_punch_id = fields.Many2one(
        "ddfsc.biometric.punch", string="Check-in Punch", readonly=True, copy=False
    )
    check_out_punch_id = fields.Many2one(
        "ddfsc.biometric.punch", string="Check-out Punch", readonly=True, copy=False
    )
    correction_reason = fields.Text(
        tracking=True,
        help="Required business explanation when HR corrects biometric attendance.",
    )
    correction_ids = fields.One2many(
        "ddfsc.attendance.correction", "attendance_id", string="Correction Requests"
    )
    correction_count = fields.Integer(compute="_compute_correction_count")
    shift_assignment_id = fields.Many2one(
        "ddfsc.shift.assignment", compute="_compute_schedule_metrics", string="Applied Schedule"
    )
    scheduled_start = fields.Datetime(compute="_compute_schedule_metrics")
    scheduled_end = fields.Datetime(compute="_compute_schedule_metrics")
    scheduled_hours = fields.Float(compute="_compute_schedule_metrics")
    late_minutes = fields.Float(compute="_compute_schedule_metrics")
    early_departure_minutes = fields.Float(compute="_compute_schedule_metrics")
    attendance_exception = fields.Selection(
        [("none", "On Time"), ("late", "Late Arrival"),
         ("early", "Early Departure"), ("late_early", "Late and Early"),
         ("incomplete", "Missing Check-out"), ("no_schedule", "No Assigned Schedule")],
        compute="_compute_schedule_metrics",
    )

    @api.depends("correction_ids")
    def _compute_correction_count(self):
        for attendance in self:
            attendance.correction_count = len(attendance.correction_ids)

    @api.depends("employee_id", "check_in", "check_out", "date")
    def _compute_schedule_metrics(self):
        for attendance in self:
            attendance.shift_assignment_id = False
            attendance.scheduled_start = False
            attendance.scheduled_end = False
            attendance.scheduled_hours = 0.0
            attendance.late_minutes = 0.0
            attendance.early_departure_minutes = 0.0
            attendance.attendance_exception = "no_schedule"
            if not attendance.employee_id or not attendance.check_in or not attendance.date:
                continue
            scheduled_start, scheduled_end, assignment, calendar = self.env[
                "ddfsc.attendance.exception"
            ]._scheduled_window_for_check_in(attendance.employee_id, attendance.check_in)
            if not calendar:
                continue
            attendance.shift_assignment_id = assignment
            if not scheduled_start:
                continue
            attendance.scheduled_start = scheduled_start
            attendance.scheduled_end = scheduled_end
            # Worked hours inside the shift block (meal breaks excluded by the calendar).
            attendance.scheduled_hours = round(calendar.get_work_hours_count(
                pytz.utc.localize(scheduled_start), pytz.utc.localize(scheduled_end),
                compute_leaves=False,
            ), 2)
            late_grace = assignment.late_grace_minutes if assignment else 0
            early_grace = assignment.early_departure_grace_minutes if assignment else 0
            attendance.late_minutes = max(
                (attendance.check_in - scheduled_start).total_seconds() / 60 - late_grace, 0
            )
            if not attendance.check_out:
                attendance.attendance_exception = "incomplete"
                continue
            attendance.early_departure_minutes = max(
                (scheduled_end - attendance.check_out).total_seconds() / 60 - early_grace, 0
            )
            if attendance.late_minutes and attendance.early_departure_minutes:
                attendance.attendance_exception = "late_early"
            elif attendance.late_minutes:
                attendance.attendance_exception = "late"
            elif attendance.early_departure_minutes:
                attendance.attendance_exception = "early"
            else:
                attendance.attendance_exception = "none"

    def action_request_correction(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Request Attendance Correction"),
            "res_model": "ddfsc.attendance.correction",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_attendance_id": self.id,
                "default_original_check_in": self.check_in,
                "default_original_check_out": self.check_out,
                "default_requested_check_in": self.check_in,
                "default_requested_check_out": self.check_out,
            },
        }

    def action_view_corrections(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Correction Requests"),
            "res_model": "ddfsc.attendance.correction", "view_mode": "list,form",
            "domain": [("attendance_id", "=", self.id)],
            "context": {"default_attendance_id": self.id},
        }

    def write(self, vals):
        for attendance in self:
            dates_to_check = [attendance.date]
            if vals.get("check_in"):
                dates_to_check.append(fields.Datetime.to_datetime(vals["check_in"]).date())
            if any(self.env["ddfsc.attendance.period"].is_locked_for(attendance.employee_id, item) for item in dates_to_check if item):
                raise ValidationError(_("Attendance is locked for this payroll period. Ask an Attendance Administrator to reopen the period with a reason."))
        biometric_records = self.filtered(lambda attendance: attendance.source == "biometric")
        changes_time = {"check_in", "check_out"}.intersection(vals)
        if (
            biometric_records
            and changes_time
            and not self.env.context.get("biometric_processing")
        ):
            raise ValidationError(
                _("Biometric times can only be changed through an approved correction request.")
            )
        result = super().write(vals)
        if "check_out" in vals:
            self.env["ddfsc.attendance.exception"].resolve_for_attendance(self)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            employee = self.env["hr.employee"].browse(vals.get("employee_id"))
            check_in = vals.get("check_in")
            attendance_date = fields.Datetime.to_datetime(check_in).date() if check_in else False
            if self.env["ddfsc.attendance.period"].is_locked_for(employee, attendance_date):
                raise ValidationError(_("Attendance is locked for this payroll period. Ask an Attendance Administrator to reopen the period with a reason."))
        return super().create(vals_list)

    def unlink(self):
        for attendance in self:
            if self.env["ddfsc.attendance.period"].is_locked_for(attendance.employee_id, attendance.date):
                raise ValidationError(_("Attendance is locked for this payroll period and cannot be deleted."))
        return super().unlink()
