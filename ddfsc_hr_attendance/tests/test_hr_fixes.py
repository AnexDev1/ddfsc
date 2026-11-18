from datetime import date, datetime

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestHrFixes(TransactionCase):
    """Employee numbers and factory holidays, as an HR officer (not admin)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hr_officer = new_test_user(
            cls.env, login="hf_hr_officer",
            groups="base.group_user,hr.group_hr_user,hr_attendance.group_hr_attendance_manager,"
                   "hr_holidays.group_hr_holidays_manager")
        cls.calendar = cls.env["resource.calendar"].create({
            "name": "Mon-Fri test", "tz": "Africa/Addis_Ababa",
            "attendance_ids": [(0, 0, {"name": "Day", "dayofweek": str(day), "hour_from": 8, "hour_to": 16,
                                       "day_period": "morning"}) for day in range(5)],
        })

    def test_new_employee_gets_the_next_number(self):
        Employee = self.env["hr.employee"].with_user(self.hr_officer)
        self.assertEqual(Employee.default_get(["employee_number"])["employee_number"], "New")
        first = Employee.create({"name": "Numbered One"})
        second = Employee.create({"name": "Numbered Two", "employee_number": "New"})
        blank = Employee.create({"name": "Numbered Three", "employee_number": False})
        typed = Employee.create({"name": "Existing Staff", "employee_number": "DDF-0042"})
        numbers = [first.employee_number, second.employee_number, blank.employee_number]
        self.assertTrue(all(number and number != "New" for number in numbers))
        self.assertEqual(len(set(numbers)), 3)
        self.assertEqual(typed.employee_number, "DDF-0042")

    def test_factory_holiday_becomes_an_odoo_public_holiday(self):
        Holiday = self.env["ddfsc.public.holiday"].with_user(self.hr_officer)
        holiday = Holiday.create({"name": "Meskel (test)", "date": date(2026, 9, 29)})  # a Tuesday
        leave = holiday.calendar_leave_id
        self.assertTrue(leave)
        self.assertFalse(leave.resource_id)
        self.assertEqual(leave.date_from, datetime(2026, 9, 28, 21, 0))  # 00:00 Addis Ababa in UTC
        hours = self.calendar.get_work_hours_count(
            datetime(2026, 9, 29, 0, 0), datetime(2026, 9, 29, 23, 59), compute_leaves=True)
        self.assertEqual(hours, 0.0, "The holiday is not a working day for time off and payroll")

        holiday.date = date(2026, 9, 30)
        self.assertEqual(holiday.calendar_leave_id, leave)
        self.assertEqual(leave.date_from, datetime(2026, 9, 29, 21, 0))

        holiday.non_working = False
        self.assertFalse(holiday.calendar_leave_id)
        self.assertFalse(leave.exists())

        holiday.non_working = True
        recreated = holiday.calendar_leave_id
        holiday.unlink()
        self.assertFalse(recreated.exists())
