from datetime import datetime, timedelta

from odoo.exceptions import ValidationError
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
