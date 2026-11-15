from datetime import date, datetime
from unittest.mock import patch

import pytz

from odoo import Command
from odoo.tests.common import TransactionCase, tagged

TZ = "Africa/Addis_Ababa"


@tagged("post_install", "-at_install")
class TestThreeShifts(TransactionCase):
    """The factory runs 06-14, 14-22 and 22-06.  The night shift crosses midnight."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tz = pytz.timezone(TZ)

        def calendar(name, pieces):
            lines = [
                Command.create({"name": "%s %s" % (name, day), "dayofweek": str(day),
                                "hour_from": start, "hour_to": end, "day_period": "morning"})
                for day in range(7) for start, end in pieces
            ]
            return cls.env["resource.calendar"].create(
                {"name": name, "tz": TZ, "attendance_ids": [Command.clear()] + lines})

        cls.calendars = {
            "S1": calendar("Shift 1", [(6, 14)]),
            "S2": calendar("Shift 2", [(14, 22)]),
            "S3": calendar("Shift 3", [(0, 6), (22, 24)]),
        }
        cls.env["ddfsc.overtime.policy"].create(
            {"name": "Test policy", "date_from": date(2026, 1, 1), "minimum_minutes": 30})

    def _utc(self, local):
        return self.tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)

    def _employee(self, name, shift):
        employee = self.env["hr.employee"].create(
            {"name": name, "resource_calendar_id": self.calendars[shift].id, "tz": TZ})
        self.env["ddfsc.shift.assignment"].create({
            "employee_id": employee.id, "calendar_id": self.calendars[shift].id,
            "date_from": date(2026, 11, 1),
        })
        return employee

    def _attend(self, employee, check_in, check_out):
        return self.env["hr.attendance"].create({
            "employee_id": employee.id, "check_in": self._utc(check_in), "check_out": self._utc(check_out),
        })

    def test_each_shift_on_time_is_not_late(self):
        for shift, start, end in (("S1", (1, 5, 55), (1, 14, 5)),
                                  ("S2", (1, 13, 55), (1, 22, 5)),
                                  ("S3", (1, 21, 55), (2, 6, 5))):
            employee = self._employee("On time %s" % shift, shift)
            attendance = self._attend(employee, datetime(2026, 12, start[0], start[1], start[2]),
                                      datetime(2026, 12, end[0], end[1], end[2]))
            self.assertEqual(attendance.attendance_exception, "none", shift)
            self.assertEqual(attendance.late_minutes, 0, shift)

    def test_night_shift_window_and_lateness(self):
        employee = self._employee("Night late", "S3")
        attendance = self._attend(employee, datetime(2026, 12, 1, 22, 20), datetime(2026, 12, 2, 6, 5))
        self.assertEqual(attendance.scheduled_start, self._utc(datetime(2026, 12, 1, 22, 0)))
        self.assertEqual(attendance.scheduled_end, self._utc(datetime(2026, 12, 2, 6, 0)))
        self.assertEqual(attendance.late_minutes, 20)
        self.assertEqual(attendance.scheduled_hours, 8)

    def test_night_shift_is_not_absent_and_overtime_is_real(self):
        on_time = self._employee("Night on time", "S3")
        stays = self._employee("Night stays late", "S3")
        self._attend(on_time, datetime(2026, 12, 1, 21, 55), datetime(2026, 12, 2, 6, 5))
        self._attend(stays, datetime(2026, 12, 1, 21, 55), datetime(2026, 12, 2, 8, 0))
        Exception = self.env["ddfsc.attendance.exception"]
        with patch("odoo.fields.Date.context_today", return_value=date(2026, 12, 3)):
            Exception.refresh_schedule_exceptions(date(2026, 12, 1))
            candidates = self.env["ddfsc.overtime.request"].generate_candidates(date(2026, 12, 1))
        flagged = Exception.search([("employee_id", "in", (on_time | stays).ids)])
        self.assertFalse(flagged, flagged.mapped("issue_type"))
        self.assertEqual(candidates.employee_id, stays)
        self.assertAlmostEqual(candidates.eligible_hours, 2.08, places=2)
