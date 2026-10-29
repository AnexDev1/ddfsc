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
        Assignment = self.env["ddfsc.shift.assignment"]
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
            assignment = Assignment.search(
                [("employee_id", "=", attendance.employee_id.id),
                 ("active", "=", True), ("date_from", "<=", attendance.date),
                 "|", ("date_to", "=", False), ("date_to", ">=", attendance.date)],
                order="date_from desc", limit=1,
            )
            calendar = assignment.calendar_id or attendance.employee_id.resource_calendar_id
            if not calendar:
                continue
            attendance.shift_assignment_id = assignment
            timezone = pytz.timezone(calendar.tz or attendance.employee_id._get_tz())
            local_midnight = timezone.localize(datetime.combine(attendance.date, time.min))
            range_start = local_midnight.astimezone(pytz.utc)
            range_end = (local_midnight + timedelta(days=2)).astimezone(pytz.utc)
            intervals = list(
                calendar._work_intervals_batch(
                    range_start, range_end, resources=attendance.employee_id.resource_id,
                    tz=timezone,
                ).get(attendance.employee_id.resource_id.id, [])
            )
            starts_today = [
                index for index, interval in enumerate(intervals)
                if interval[0].astimezone(timezone).date() == attendance.date
            ]
            if not starts_today:
                continue
            selected = [intervals[starts_today[0]]]
            for interval in intervals[starts_today[0] + 1:]:
                if interval[0] - selected[-1][1] <= timedelta(hours=8):
                    selected.append(interval)
                else:
                    break
            scheduled_start = selected[0][0].astimezone(pytz.utc).replace(tzinfo=None)
            scheduled_end = selected[-1][1].astimezone(pytz.utc).replace(tzinfo=None)
            attendance.scheduled_start = scheduled_start
            attendance.scheduled_end = scheduled_end
            attendance.scheduled_hours = sum(
                (stop - start).total_seconds() / 3600 for start, stop, _meta in selected
            )
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
        return super().write(vals)
