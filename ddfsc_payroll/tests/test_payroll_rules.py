from datetime import date, datetime

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPayrollRules(TransactionCase):
    """Overtime categories, tax-exempt allowance limit and payroll eligibility."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env["ddfsc.overtime.pay.rate"].search([]).write({"active": False})
        cls.rate = cls.env["ddfsc.overtime.pay.rate"].create({
            "name": "Test rate", "date_from": date(2020, 1, 1), "multiplier": 1.5,
            "monthly_standard_hours": 208.0,
        })
        cls.env["ddfsc.nontaxable.allowance.limit"].search([]).write({"active": False})
        cls.env["ddfsc.nontaxable.allowance.limit"].create({
            "name": "Test limit", "date_from": date(2020, 1, 1), "percent_of_basic": 25.0, "maximum_amount": 2200.0,
        })
        calendar = cls.env["resource.calendar"].create({"name": "Addis test schedule", "tz": "Africa/Addis_Ababa"})
        cls.employee = cls.env["hr.employee"].create({
            "name": "Payroll Rules Employee", "tz": "Africa/Addis_Ababa", "resource_calendar_id": calendar.id})
        cls.policy = cls.env["ddfsc.overtime.policy"].create({"name": "Test policy", "date_from": date(2020, 1, 1)})

    def _overtime(self, work_date, scheduled=True, **values):
        # Shift 08:00-16:00 Addis Ababa (05:00-13:00 UTC); in at 06:00, out at 23:00 local.
        day = work_date.day
        vals = {
            "employee_id": self.employee.id, "work_date": work_date, "policy_id": self.policy.id,
            "first_check_in": datetime(2026, 6, day, 3, 0), "last_check_out": datetime(2026, 6, day, 20, 0),
            "eligible_hours": 9.0, "approved_hours": 9.0, "state": "approved",
        }
        if scheduled:
            vals.update(scheduled_start=datetime(2026, 6, day, 5, 0), scheduled_end=datetime(2026, 6, day, 13, 0))
        vals.update(values)
        return self.env["ddfsc.overtime.request"].create(vals)

    def test_overtime_is_split_into_day_and_night_hours(self):
        request = self._overtime(date(2026, 6, 10))
        self.assertEqual((request.ot_day_hours, request.ot_night_hours), (8.0, 1.0))
        payment = self.rate.calculate_split_payment(request._ddfsc_hours_split(), 20800.0, date(2026, 6, 30), self.company)
        self.assertEqual(payment, 8 * 100 * 1.5 + 1 * 100 * 1.75)

    def test_rest_day_and_public_holiday_rates(self):
        rest = self._overtime(date(2026, 6, 13), scheduled=False)
        self.assertEqual(rest.ot_rest_day_hours, 9.0)
        self.env["ddfsc.public.holiday"].create({"name": "Holiday (test)", "date": date(2026, 6, 17)})
        holiday = self._overtime(date(2026, 6, 17))
        self.assertEqual(holiday.ot_holiday_hours, 9.0)
        payment = self.rate.calculate_split_payment(
            (rest | holiday)._ddfsc_hours_split(), 20800.0, date(2026, 6, 30), self.company)
        self.assertEqual(payment, 9 * 100 * 2.0 + 9 * 100 * 2.5)

    def test_reduced_approval_keeps_the_proportion(self):
        request = self._overtime(date(2026, 6, 11), approved_hours=4.5)
        self.assertEqual((request.ot_day_hours, request.ot_night_hours), (4.0, 0.5))

    def test_tax_exempt_allowance_limit(self):
        Limit = self.env["ddfsc.nontaxable.allowance.limit"]
        self.assertEqual(Limit.exempt_amount(3000.0, 22000.0, date(2026, 6, 30), self.company), 2200.0)
        self.assertEqual(Limit.exempt_amount(600.0, 4000.0, date(2026, 6, 30), self.company), 600.0)
        self.assertEqual(Limit.exempt_amount(1500.0, 4000.0, date(2026, 6, 30), self.company), 1000.0)

    def test_ineligible_employee_is_not_paid_except_final_payslip(self):
        payslip = self.env["hr.payslip"].create({
            "name": "Eligibility", "employee_id": self.employee.id, "contract_id": self.employee.version_id.id,
            "date_from": date(2026, 6, 1), "date_to": date(2026, 6, 30), "company_id": self.company.id,
        })
        self.employee.payroll_eligible = False
        with self.assertRaises(UserError):
            payslip.compute_sheet()
        self.employee.departure_date = date(2026, 6, 20)
        self.assertTrue(payslip._ddfsc_payroll_allowed())
