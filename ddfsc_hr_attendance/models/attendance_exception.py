from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models


class DdfscAttendanceException(models.Model):
    """A review queue for attendance issues; source records always remain untouched."""

    _name = "ddfsc.attendance.exception"
    _description = "Attendance Exception"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "detected_at desc, id desc"

    name = fields.Char(required=True, readonly=True)
    issue_type = fields.Selection(
        [
            ("missing_checkout", "Missing check-out"),
            ("unmatched_checkout", "Check-out without a check-in"),
            ("repeated_checkin", "Repeated check-in"),
            ("invalid_sequence", "Invalid punch sequence"),
            ("unmapped_employee", "Employee not mapped"),
            ("absence", "Unexplained absence"),
            ("late_arrival", "Late arrival"),
            ("early_departure", "Early departure"),
            ("leave_attendance_conflict", "Attendance during approved leave"),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    severity = fields.Selection(
        [("warning", "Needs review"), ("critical", "Blocks attendance")],
        required=True,
        readonly=True,
        default="warning",
    )
    state = fields.Selection(
        [("open", "Open"), ("resolved", "Resolved"), ("ignored", "Ignored")],
        required=True,
        default="open",
        tracking=True,
        index=True,
    )
    attendance_id = fields.Many2one("hr.attendance", ondelete="restrict", readonly=True, index=True)
    punch_id = fields.Many2one("ddfsc.biometric.punch", ondelete="restrict", readonly=True, index=True)
    employee_id = fields.Many2one("hr.employee", readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True, index=True)
    detected_at = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)
    scheduled_date = fields.Date(readonly=True, index=True)
    description = fields.Text(required=True, readonly=True)
    resolved_by = fields.Many2one("res.users", readonly=True)
    resolved_at = fields.Datetime(readonly=True)
    resolution_note = fields.Text(tracking=True)

    @api.model
    def _active_exception(self, domain):
        return self.search(domain + [("state", "=", "open")], limit=1)

    @api.model
    def create_from_punch(self, punch, issue_type, description):
        """Keep the device event immutable while giving HR one actionable queue."""
        existing = self._active_exception([
            ("punch_id", "=", punch.id), ("issue_type", "=", issue_type),
        ])
        if existing:
            return existing
        labels = dict(self._fields["issue_type"].selection)
        return self.sudo().create({
            "name": "%s: %s" % (labels[issue_type], punch.event_time),
            "issue_type": issue_type,
            "severity": "critical" if issue_type != "unmapped_employee" else "warning",
            "punch_id": punch.id,
            "employee_id": punch.employee_id.id,
            "company_id": punch.company_id.id,
            "description": description,
        })

    @api.model
    def refresh_missing_checkouts(self):
        """Flag genuinely overdue biometric check-ins, not a fresh employee scan."""
        cutoff = fields.Datetime.now() - timedelta(hours=16)
        attendances = self.env["hr.attendance"].search([
            ("source", "=", "biometric"), ("check_out", "=", False),
            ("check_in", "<=", cutoff),
        ])
        for attendance in attendances:
            existing = self._active_exception([
                ("attendance_id", "=", attendance.id), ("issue_type", "=", "missing_checkout"),
            ])
            if not existing:
                self.sudo().create({
                    "name": _("Missing check-out: %s") % attendance.employee_id.name,
                    "issue_type": "missing_checkout",
                    "severity": "warning",
                    "attendance_id": attendance.id,
                    "employee_id": attendance.employee_id.id,
                    "company_id": attendance.employee_id.company_id.id,
                    "description": _("No biometric check-out has been received since %(time)s. Review the raw punches or request a time correction.", time=attendance.check_in),
                })
        return True

    def action_refresh_missing_checkouts(self):
        self.refresh_missing_checkouts()
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def _scheduled_window(self, employee, review_date):
        """Return the applicable schedule window for this employee/date in UTC."""
        assignment = self.env["ddfsc.shift.assignment"].search([
            ("employee_id", "=", employee.id), ("active", "=", True),
            ("date_from", "<=", review_date), "|", ("date_to", "=", False),
            ("date_to", ">=", review_date),
        ], order="date_from desc", limit=1)
        calendar = assignment.calendar_id or employee.resource_calendar_id
        if not calendar:
            return False, False, assignment
        timezone = pytz.timezone(calendar.tz or employee._get_tz())
        local_midnight = timezone.localize(datetime.combine(review_date, time.min))
        intervals = list(calendar._work_intervals_batch(
            local_midnight.astimezone(pytz.utc),
            (local_midnight + timedelta(days=2)).astimezone(pytz.utc),
            resources=employee.resource_id, tz=timezone,
        ).get(employee.resource_id.id, []))
        starts_today = [i for i, interval in enumerate(intervals)
                        if interval[0].astimezone(timezone).date() == review_date]
        if not starts_today:
            return False, False, assignment
        selected = [intervals[starts_today[0]]]
        for interval in intervals[starts_today[0] + 1:]:
            if interval[0] - selected[-1][1] <= timedelta(hours=8):
                selected.append(interval)
            else:
                break
        return (
            selected[0][0].astimezone(pytz.utc).replace(tzinfo=None),
            selected[-1][1].astimezone(pytz.utc).replace(tzinfo=None), assignment,
        )

    @api.model
    def _set_schedule_exception(self, employee, review_date, issue_type, required, description):
        domain = [
            ("employee_id", "=", employee.id), ("scheduled_date", "=", review_date),
            ("issue_type", "=", issue_type),
        ]
        exception = self._active_exception(domain)
        if required and not exception:
            labels = dict(self._fields["issue_type"].selection)
            self.sudo().create({
                "name": "%s: %s (%s)" % (labels[issue_type], employee.name, review_date),
                "issue_type": issue_type,
                "severity": "warning",
                "employee_id": employee.id,
                "company_id": employee.company_id.id,
                "scheduled_date": review_date,
                "description": description,
            })
        elif not required and exception:
            exception.write({
                "state": "resolved", "resolved_by": self.env.user.id,
                "resolved_at": fields.Datetime.now(),
                "resolution_note": _("Schedule review recalculated; this exception no longer applies."),
            })

    @api.model
    def refresh_schedule_exceptions(self, review_date=None):
        """Compare a completed scheduled day with attendance and validated leave.

        This produces review records only. It never creates attendance or changes
        a raw biometric event, so HR remains in control of corrections.
        """
        review_date = review_date or (fields.Date.context_today(self) - timedelta(days=1))
        today = fields.Date.context_today(self)
        if review_date >= today:
            return True
        employees = self.env["hr.employee"].search([("active", "=", True)])
        Attendance = self.env["hr.attendance"]
        Leave = self.env["hr.leave"]
        PublicHoliday = self.env["ddfsc.public.holiday"]
        for employee in employees:
            if PublicHoliday.is_non_working_day(employee.company_id, review_date):
                for issue_type in ("absence", "late_arrival", "early_departure", "leave_attendance_conflict"):
                    self._set_schedule_exception(employee, review_date, issue_type, False, False)
                continue
            scheduled_start, scheduled_end, assignment = self._scheduled_window(employee, review_date)
            if not scheduled_start:
                continue
            on_leave = Leave.search_count([
                ("employee_id", "=", employee.id), ("state", "=", "validate"),
                ("date_from", "<=", scheduled_end), ("date_to", ">=", scheduled_start),
            ])
            attendances = Attendance.search([
                ("employee_id", "=", employee.id), ("check_in", "<=", scheduled_end),
                "|", ("check_out", "=", False), ("check_out", ">=", scheduled_start),
            ])
            if on_leave and attendances:
                self._set_schedule_exception(employee, review_date, "absence", False, False)
                self._set_schedule_exception(
                    employee, review_date, "leave_attendance_conflict", True,
                    _("Attendance was recorded during an approved leave period. HR must confirm whether the leave or attendance needs correction."),
                )
                continue
            if on_leave:
                self._set_schedule_exception(employee, review_date, "absence", False, False)
                self._set_schedule_exception(employee, review_date, "leave_attendance_conflict", False, False)
                continue
            self._set_schedule_exception(employee, review_date, "leave_attendance_conflict", False, False)
            if not attendances:
                self._set_schedule_exception(
                    employee, review_date, "absence", True,
                    _("No attendance was recorded for the scheduled shift from %(start)s to %(end)s.", start=scheduled_start, end=scheduled_end),
                )
                continue
            self._set_schedule_exception(employee, review_date, "absence", False, False)
            first_in = min(attendances.mapped("check_in"))
            checkouts = [value for value in attendances.mapped("check_out") if value]
            last_out = max(checkouts) if checkouts else False
            late_grace = assignment.late_grace_minutes if assignment else 0
            early_grace = assignment.early_departure_grace_minutes if assignment else 0
            late_minutes = max((first_in - scheduled_start).total_seconds() / 60 - late_grace, 0)
            early_minutes = max((scheduled_end - last_out).total_seconds() / 60 - early_grace, 0) if last_out else 0
            self._set_schedule_exception(
                employee, review_date, "late_arrival", bool(late_minutes),
                _("First check-in was %(minutes).0f minutes after the permitted scheduled start.", minutes=late_minutes),
            )
            self._set_schedule_exception(
                employee, review_date, "early_departure", bool(early_minutes),
                _("Last check-out was %(minutes).0f minutes before the permitted scheduled end.", minutes=early_minutes),
            )
        return True

    def action_generate_yesterday_schedule_exceptions(self):
        self.refresh_schedule_exceptions()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_correction(self):
        self.ensure_one()
        if not self.attendance_id:
            return False
        return self.attendance_id.action_request_correction()

    def action_resolve(self):
        self.filtered(lambda exception: exception.state == "open").write({
            "state": "resolved", "resolved_by": self.env.user.id,
            "resolved_at": fields.Datetime.now(),
        })

    def action_ignore(self):
        self.filtered(lambda exception: exception.state == "open").write({
            "state": "ignored", "resolved_by": self.env.user.id,
            "resolved_at": fields.Datetime.now(),
        })

    @api.model
    def resolve_for_attendance(self, attendance):
        for item in attendance:
            self.search([
                ("attendance_id", "=", item.id), ("issue_type", "=", "missing_checkout"),
                ("state", "=", "open"),
            ]).write({
                "state": "resolved", "resolved_by": self.env.user.id,
                "resolved_at": fields.Datetime.now(),
                "resolution_note": _("Check-out was recorded."),
            })
