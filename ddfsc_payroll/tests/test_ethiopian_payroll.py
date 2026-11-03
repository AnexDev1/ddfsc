from datetime import date

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEthiopianPayrollConfiguration(TransactionCase):
    def test_effective_dated_tax_bands_calculate_progressively(self):
        TaxBand = self.env["ddfsc.ethiopian.tax.band"]
        self.assertEqual(TaxBand.calculate_monthly_tax(2000, date(2026, 1, 1)), 0)
        self.assertEqual(TaxBand.calculate_monthly_tax(4000, date(2026, 1, 1)), 300)
        self.assertEqual(TaxBand.calculate_monthly_tax(20000, date(2026, 1, 1)), 4950)

    def test_pension_configuration_calculates_both_sides(self):
        result = self.env["ddfsc.ethiopian.pension.config"].calculate_contributions(20000, date(2026, 1, 1))
        self.assertEqual(result["employee"], 1400)
        self.assertEqual(result["employer"], 2200)

    def test_overtime_payment_uses_effective_rate_and_standard_hours(self):
        amount = self.env["ddfsc.overtime.pay.rate"].calculate_payment(10, 20800, date(2026, 1, 1))
        self.assertEqual(amount, 1500)

    def test_approved_deduction_template_is_available(self):
        component_type = self.env.ref("ddfsc_payroll.component_type_approved_deduction")
        self.assertEqual(component_type.component_kind, "deduction")
        self.assertEqual(component_type.code, "OTHER_DED")
        self.assertEqual(component_type.salary_rule_id.code, "OTHER_DED")

    def test_shift_differential_template_is_available(self):
        component_type = self.env.ref("ddfsc_payroll.component_type_shift_differential")
        self.assertEqual(component_type.component_kind, "earning")
        self.assertEqual(component_type.code, "SHIFT_DIFF")
