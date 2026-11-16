from datetime import date

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestTimeOffPay(TransactionCase):
    """Basic salary follows employment dates and time off that is not fully paid."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hr_officer = new_test_user(
            cls.env, login="tp_hr_officer",
            groups="base.group_user,hr.group_hr_user,hr_holidays.group_hr_holidays_manager")
        cls.calendar = cls.env["resource.calendar"].create({
            "name": "Mon-Fri 08-17 test", "tz": "Africa/Addis_Ababa",
            "attendance_ids": [(0, 0, {"name": "Day", "dayofweek": str(day), "hour_from": 8, "hour_to": 12,
                                       "day_period": "morning"}) for day in range(5)]
            + [(0, 0, {"name": "Day", "dayofweek": str(day), "hour_from": 13, "hour_to": 17,
                       "day_period": "afternoon"}) for day in range(5)],
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "Time Off Pay Employee", "resource_calendar_id": cls.calendar.id, "tz": "Africa/Addis_Ababa"})
        cls.basic_rule = cls.env.ref("ddfsc_payroll.rule_basic_salary")
        cls.structure = cls.env["hr.payroll.structure"].create({
            "name": "Time off test structure", "code": "TOFF_TEST", "rule_ids": [(4, cls.basic_rule.id)]})
        cls.employee.version_id.write({
            "contract_date_start": date(2026, 1, 1), "wage": 22000.0,
            "struct_id": cls.structure.id, "resource_calendar_id": cls.calendar.id,
        })
        cls.contract = cls.employee.version_id
        cls.unpaid = cls.env["hr.leave.type"].create({
            "name": "Unpaid (test)", "requires_allocation": False, "unpaid": True, "ddfsc_pay_percent": 0.0})
        cls.half = cls.env["hr.leave.type"].create({
            "name": "Sick 50% (test)", "requires_allocation": False, "ddfsc_pay_percent": 50.0})
        cls.paid = cls.env["hr.leave.type"].create({"name": "Annual (test)", "requires_allocation": False})

    def _payslip(self, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)):
        return self.env["hr.payslip"].create({
            "name": "Time off payslip", "employee_id": self.employee.id, "contract_id": self.contract.id,
            "struct_id": self.structure.id, "date_from": date_from, "date_to": date_to,
            "company_id": self.employee.company_id.id,
        })

    def _leave(self, leave_type, day_from, day_to):
        leave = self.env["hr.leave"].with_user(self.hr_officer).create({
            "name": "Test leave", "employee_id": self.employee.id, "holiday_status_id": leave_type.id,
            "request_date_from": day_from, "request_date_to": day_to,
        })
        leave.with_user(self.hr_officer).action_approve()
        if leave.state != "validate":
            leave.with_user(self.hr_officer).action_validate()
        return leave

    def test_full_month_without_leave_pays_full_basic(self):
        payslip = self._payslip()
        self.assertAlmostEqual(payslip.ddfsc_paid_ratio, 1.0)
        self.assertAlmostEqual(payslip.get_period_basic_salary(self.contract), 22000.0)

    def test_unpaid_and_half_paid_leave_reduce_basic(self):
        # June 2026 has 22 working days (Mon-Fri).
        self._leave(self.unpaid, date(2026, 6, 8), date(2026, 6, 9))      # 2 days at 0 %
        self._leave(self.half, date(2026, 6, 15), date(2026, 6, 16))      # 2 days at 50 %
        self._leave(self.paid, date(2026, 6, 22), date(2026, 6, 22))      # paid: no effect
        payslip = self._payslip()
        self.assertAlmostEqual(payslip.ddfsc_paid_ratio, (22 - 2 - 1) / 22, places=4)
        self.assertAlmostEqual(payslip.get_period_basic_salary(self.contract), 22000.0 * 19 / 22, places=2)

    def test_mid_month_joiner_is_paid_from_start_date(self):
        self.contract.contract_date_start = date(2026, 6, 15)  # 12 working days 15-30 June
        payslip = self._payslip()
        self.assertAlmostEqual(payslip.ddfsc_paid_ratio, 12 / 22, places=4)

    def test_unpaid_types_are_set_to_zero_on_upgrade(self):
        legacy = self.env["hr.leave.type"].create({"name": "Legacy unpaid", "unpaid": True, "requires_allocation": False})
        self.assertEqual(legacy.ddfsc_pay_percent, 100.0)
        self.env["hr.leave.type"]._ddfsc_sync_unpaid_types()
        self.assertEqual(legacy.ddfsc_pay_percent, 0.0)

    def test_overtime_uses_salary_in_force(self):
        payslip = self._payslip()
        self.assertEqual(payslip.get_effective_basic_salary(self.contract), 22000.0)

    def test_ethiopian_leave_types(self):
        ref = lambda name: self.env.ref("ddfsc_payroll.%s" % name)
        self.assertEqual(ref("leave_type_et_annual").country_id.code, "ET")
        self.assertTrue(ref("leave_type_et_annual").requires_allocation)
        self.assertEqual([ref("leave_type_et_sick_%s" % tier).ddfsc_pay_percent for tier in ("full", "half", "unpaid")],
                         [100.0, 50.0, 0.0])
        self.assertTrue(ref("leave_type_et_sick_half").support_document)
        self.assertEqual(ref("leave_type_et_special_unpaid").ddfsc_pay_percent, 0.0)
        # Two days in the 50 % sick tier cost one day of basic salary (22 working days in June).
        self._leave(ref("leave_type_et_sick_half"), date(2026, 6, 8), date(2026, 6, 9))
        self.assertAlmostEqual(self._payslip().ddfsc_paid_ratio, 21 / 22, places=4)
