from datetime import datetime, timedelta

from odoo.exceptions import ValidationError
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBiometricAttendance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Biometric Test Employee", "biometric_user_id": "DDFSC-TEST-101"}
        )
        cls.device = cls.env["ddfsc.biometric.device"].create(
            {"name": "Test Import Device", "code": "TEST-IMPORT", "device_type": "file"}
        )
        cls.start = datetime(2026, 10, 28, 5, 30)

    def _punch(self, event_time, punch_type, user_id="DDFSC-TEST-101"):
        return self.env["ddfsc.biometric.punch"].create(
            {
                "device_id": self.device.id,
                "device_user_id": user_id,
                "event_time": event_time,
                "punch_type": punch_type,
            }
        )

    def test_in_out_pair_creates_auditable_attendance(self):
        punch_in = self._punch(self.start, "in")
        punch_out = self._punch(self.start + timedelta(hours=8), "out")
        (punch_in | punch_out).action_process()

        self.assertEqual(punch_in.state, "processed")
        self.assertEqual(punch_out.state, "processed")
        self.assertEqual(punch_in.attendance_id, punch_out.attendance_id)
        self.assertEqual(punch_in.attendance_id.source, "biometric")
        self.assertEqual(punch_in.attendance_id.check_in_punch_id, punch_in)
        self.assertEqual(punch_in.attendance_id.check_out_punch_id, punch_out)

    def test_unmapped_punch_stays_in_exception_queue(self):
        punch = self._punch(self.start, "in", user_id="NOT-MAPPED")
        punch.action_process()
        self.assertEqual(punch.state, "unmapped")
        self.assertFalse(punch.attendance_id)

    def test_unmatched_checkout_creates_an_actionable_exception(self):
        punch = self._punch(self.start, "out")
        punch.action_process()
        exception = self.env["ddfsc.attendance.exception"].search([("punch_id", "=", punch.id)])
        self.assertEqual(punch.state, "error")
        self.assertEqual(exception.issue_type, "unmatched_checkout")
        self.assertEqual(exception.state, "open")

    def test_overdue_open_attendance_is_flagged_and_checkout_resolves_it(self):
        attendance = self.env["hr.attendance"].create({
            "employee_id": self.employee.id,
            "check_in": fields.Datetime.now() - timedelta(hours=17),
            "source": "biometric",
        })
        self.env["ddfsc.attendance.exception"].refresh_missing_checkouts()
        exception = self.env["ddfsc.attendance.exception"].search([("attendance_id", "=", attendance.id)])
        self.assertEqual(exception.issue_type, "missing_checkout")
        attendance.with_context(biometric_processing=True).write({"check_out": fields.Datetime.now()})
        self.assertEqual(exception.state, "resolved")

    def test_schedule_review_flags_unexplained_absence(self):
        calendar = self.env["resource.calendar"].create({
            "name": "DDFSC Absence Review Shift", "tz": "Africa/Addis_Ababa",
            "attendance_ids": [(0, 0, {"name": "Weekday", "dayofweek": "2", "day_period": "morning", "hour_from": 8, "hour_to": 17})],
        })
        self.env["ddfsc.shift.assignment"].create({
            "employee_id": self.employee.id, "calendar_id": calendar.id, "date_from": "2026-10-01",
        })
        self.env["ddfsc.attendance.exception"].refresh_schedule_exceptions(fields.Date.from_string("2026-10-28"))
        absence = self.env["ddfsc.attendance.exception"].search([
            ("employee_id", "=", self.employee.id), ("scheduled_date", "=", "2026-10-28"), ("issue_type", "=", "absence"),
        ])
        self.assertEqual(absence.state, "open")

    def test_non_working_public_holiday_does_not_create_absence(self):
        calendar = self.env["resource.calendar"].create({
            "name": "DDFSC Holiday Review Shift", "tz": "Africa/Addis_Ababa",
            "attendance_ids": [(0, 0, {"name": "Weekday", "dayofweek": "2", "day_period": "morning", "hour_from": 8, "hour_to": 17})],
        })
        self.env["ddfsc.shift.assignment"].create({
            "employee_id": self.employee.id, "calendar_id": calendar.id, "date_from": "2026-10-01",
        })
        self.env["ddfsc.public.holiday"].create({
            "name": "DDFSC Test Closure", "date": "2026-10-28", "company_id": self.employee.company_id.id,
        })
        self.env["ddfsc.attendance.exception"].refresh_schedule_exceptions(fields.Date.from_string("2026-10-28"))
        absence = self.env["ddfsc.attendance.exception"].search([
            ("employee_id", "=", self.employee.id), ("scheduled_date", "=", "2026-10-28"), ("issue_type", "=", "absence"),
        ])
        self.assertFalse(absence)

    def test_overtime_candidate_uses_time_outside_the_assigned_shift(self):
        calendar = self.env["resource.calendar"].create({
            "name": "DDFSC Overtime Shift", "tz": "Africa/Addis_Ababa",
            "attendance_ids": [(0, 0, {"name": "Wednesday", "dayofweek": "2", "day_period": "morning", "hour_from": 8, "hour_to": 17})],
        })
        self.env["ddfsc.shift.assignment"].create({
            "employee_id": self.employee.id, "calendar_id": calendar.id, "date_from": "2026-10-01",
        })
        self.env["ddfsc.overtime.policy"].create({
            "name": "Test Policy", "date_from": "2026-01-01", "minimum_minutes": 30,
        })
        self.env["hr.attendance"].create({
            "employee_id": self.employee.id, "check_in": datetime(2026, 10, 28, 5, 30),
            "check_out": datetime(2026, 10, 28, 15, 30), "source": "biometric",
        })
        candidate = self.env["ddfsc.overtime.request"].generate_candidates(fields.Date.from_string("2026-10-28"))
        self.assertEqual(candidate.employee_id, self.employee)
        self.assertAlmostEqual(candidate.eligible_hours, 1.5)
        candidate.action_submit()
        self.assertEqual(candidate.approved_hours, 1.5)

    def test_locked_attendance_period_blocks_attendance_changes(self):
        attendance = self.env["hr.attendance"].create({
            "employee_id": self.employee.id, "check_in": datetime(2026, 10, 28, 5, 30),
            "check_out": datetime(2026, 10, 28, 13, 30), "source": "biometric",
        })
        period = self.env["ddfsc.attendance.period"].create({
            "date_from": "2026-10-28", "date_to": "2026-10-28",
        })
        root = self.env.ref("base.user_root")
        period.with_user(root).action_validate()
        period.with_user(root).action_lock()
        self.assertEqual(period.state, "locked")
        with self.assertRaises(ValidationError):
            attendance.with_context(biometric_processing=True).write({"check_out": datetime(2026, 10, 28, 14, 0)})

    def test_raw_data_and_biometric_time_are_protected(self):
        punch = self._punch(self.start, "in")
        with self.assertRaises(ValidationError):
            punch.event_time = self.start + timedelta(minutes=1)

        punch.action_process()
        attendance = punch.attendance_id
        with self.assertRaises(ValidationError):
            attendance.check_in = self.start + timedelta(minutes=5)
        request = self.env["ddfsc.attendance.correction"].create(
            {
                "attendance_id": attendance.id,
                "requested_check_in": self.start + timedelta(minutes=5),
                "reason": "Approved correction for test",
            }
        )
        request.action_submit()
        request.action_approve()
        self.assertEqual(request.state, "approved")
        self.assertEqual(attendance.correction_reason, "Approved correction for test")

    def test_effective_schedule_calculates_late_and_early_minutes(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "DDFSC Test Day Shift",
                "tz": "Africa/Addis_Ababa",
                "attendance_ids": [
                    (0, 0, {"name": "Wednesday", "dayofweek": "2", "day_period": "morning", "hour_from": 8.0, "hour_to": 12.0}),
                    (0, 0, {"name": "Wednesday", "dayofweek": "2", "day_period": "afternoon", "hour_from": 13.0, "hour_to": 17.0}),
                ],
            }
        )
        self.env["ddfsc.shift.assignment"].create(
            {
                "employee_id": self.employee.id,
                "calendar_id": calendar.id,
                "date_from": "2026-10-01",
                "late_grace_minutes": 10,
                "early_departure_grace_minutes": 5,
            }
        )
        attendance = self.env["hr.attendance"].create(
            {
                "employee_id": self.employee.id,
                "check_in": datetime(2026, 10, 28, 5, 15),
                "check_out": datetime(2026, 10, 28, 13, 50),
            }
        )
        self.assertEqual(attendance.attendance_exception, "late_early")
        self.assertAlmostEqual(attendance.late_minutes, 5.0)
        self.assertAlmostEqual(attendance.early_departure_minutes, 5.0)
