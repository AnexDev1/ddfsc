from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPayrollComponents(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "Component Test Employee"})
        cls.category = cls.env["hr.salary.rule.category"].create({"name": "Allowance", "code": "ALW_TEST"})
        cls.rule = cls.env["hr.salary.rule"].create({
            "name": "Transport Component", "code": "TRANSPORT_RULE", "sequence": 20,
            "category_id": cls.category.id, "condition_select": "none", "amount_select": "code",
            "amount_python_compute": "result = inputs.TRANSPORT and inputs.TRANSPORT.amount or 0.0",
        })
        cls.env["hr.rule.input"].create({"name": "Transport", "code": "TRANSPORT", "input_id": cls.rule.id})
        cls.structure = cls.env["hr.payroll.structure"].create({
            "name": "Component Test Structure", "code": "COMP_TEST", "rule_ids": [(4, cls.rule.id)]
        })
        cls.employee.version_id.write({
            "contract_date_start": date(2026, 1, 1), "name": "Component Test Contract",
            "wage": 5000.0, "struct_id": cls.structure.id,
        })
        cls.contract = cls.employee.version_id
        cls.component_type = cls.env["ddfsc.payroll.component.type"].create({
            "name": "Transport Allowance", "code": "TRANSPORT", "component_kind": "earning",
            "salary_rule_id": cls.rule.id, "company_id": cls.employee.company_id.id,
        })

    def _payslip(self, month=1):
        return self.env["hr.payslip"].create({
            "name": "Test Payslip", "employee_id": self.employee.id,
            "contract_id": self.contract.id, "struct_id": self.structure.id,
            "date_from": date(2026, month, 1), "date_to": date(2026, month, 28),
            "company_id": self.employee.company_id.id,
        })

    def _component(self, **values):
        vals = {
            "employee_id": self.employee.id, "component_type_id": self.component_type.id,
            "amount": 500.0, "recurrence": "recurring", "date_from": date(2026, 1, 1),
            "company_id": self.employee.company_id.id,
        }
        vals.update(values)
        return self.env["ddfsc.employee.payroll.component"].create(vals)

    def test_approved_effective_component_is_added_and_aggregated(self):
        first = self._component(amount=500.0)
        second = self._component(amount=250.0)
        first.action_approve(); second.action_approve()
        payslip = self._payslip()
        line = next(item for item in payslip.get_inputs(self.contract, payslip.date_from, payslip.date_to) if item["code"] == "TRANSPORT")
        self.assertEqual(line["amount"], 750.0)
        self.assertEqual(set(line["component_ids"][0][2]), {first.id, second.id})

    def test_draft_and_outside_period_are_excluded(self):
        self._component(amount=100.0)
        later = self._component(amount=200.0, date_from=date(2026, 3, 1))
        later.action_approve()
        payslip = self._payslip()
        line = next(item for item in payslip.get_inputs(self.contract, payslip.date_from, payslip.date_to) if item["code"] == "TRANSPORT")
        self.assertFalse(line.get("amount"))

    def test_one_off_is_not_reused_after_completed_payslip(self):
        component = self._component(recurrence="one_off", date_to=date(2026, 2, 28))
        component.action_approve()
        january = self._payslip(1)
        january.write({"input_line_ids": [(0, 0, {
            "name": "Transport", "code": "TRANSPORT", "amount": 500,
            "contract_id": self.contract.id, "component_ids": [(6, 0, component.ids)],
        })], "state": "done"})
        february = self._payslip(2)
        line = next(item for item in february.get_inputs(self.contract, february.date_from, february.date_to) if item["code"] == "TRANSPORT")
        self.assertFalse(line.get("amount"))
        with self.assertRaises(UserError):
            component.action_reset_to_draft()

    def test_configuration_validation(self):
        with self.assertRaises(ValidationError):
            self.env["ddfsc.payroll.component.type"].create({
                "name": "Bad Type", "code": "bad code", "salary_rule_id": self.rule.id,
                "company_id": self.employee.company_id.id,
            })
        with self.assertRaises(ValidationError):
            self._component(amount=0)
