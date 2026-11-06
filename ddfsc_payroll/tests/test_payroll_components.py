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

    def test_payroll_batch_shows_payslip_progress(self):
        batch = self.env["hr.payslip.run"].create({
            "name": "January 2026 Payroll", "date_start": date(2026, 1, 1),
            "date_end": date(2026, 1, 31), "company_id": self.employee.company_id.id,
        })
        payslip = self._payslip()
        payslip.write({"payslip_run_id": batch.id})
        self.assertEqual(batch.ddfsc_payslip_count, 1)
        self.assertEqual(batch.ddfsc_draft_count, 1)
        self.assertIn("1 payslips: 1 draft", batch.ddfsc_batch_progress)

    def test_empty_payroll_batch_cannot_pass_validation(self):
        batch = self.env["hr.payslip.run"].create({
            "name": "Empty Payroll", "date_start": date(2026, 1, 1),
            "date_end": date(2026, 1, 31), "company_id": self.employee.company_id.id,
        })
        result = batch.action_validate_batch()
        self.assertEqual(result["params"]["type"], "danger")
        self.assertEqual(batch.ddfsc_validation_state, "failed")

    def test_final_settlement_must_be_one_time_and_documented(self):
        with self.assertRaises(ValidationError):
            self._component(adjustment_type="final_settlement", recurrence="one_off")
        component = self._component(
            adjustment_type="final_settlement", recurrence="one_off", note="HR exit approval EX-001"
        )
        component._check_final_settlement_controls()

    def test_closed_batch_locks_payslips_and_requires_reopen_reason(self):
        batch = self.env["hr.payslip.run"].create({
            "name": "Locked Payroll", "date_start": date(2026, 1, 1),
            "date_end": date(2026, 1, 31), "company_id": self.employee.company_id.id,
        })
        payslip = self._payslip()
        payslip.write({"payslip_run_id": batch.id})
        batch.write({"state": "close"})
        with self.assertRaises(UserError):
            payslip.write({"name": "Changed after close"})
        with self.assertRaises(UserError):
            batch.draft_payslip_run()
        batch.write({"ddfsc_reopen_reason": "Approved correction after close"})
        batch.draft_payslip_run()
        self.assertEqual(batch.state, "draft")
        self.assertEqual(batch.ddfsc_reopened_by, self.env.user)

    def _allowance_policy(self, **values):
        vals = {
            "name": "Factory Transport Allowance", "code": "TRANSPORT_FACTORY",
            "component_type_id": self.component_type.id, "calculation_method": "fixed",
            "fixed_amount": 500.0, "recurrence": "recurring", "eligibility_scope": "all",
            "date_from": date(2026, 1, 1), "company_id": self.employee.company_id.id,
        }
        vals.update(values)
        return self.env["ddfsc.allowance.policy"].create(vals)

    def _allowance_request(self, policy, **values):
        vals = {
            "employee_id": self.employee.id, "policy_id": policy.id, "amount": 1.0,
            "date_from": date(2026, 1, 1), "company_id": self.employee.company_id.id,
            "note": "Approved factory transport entitlement",
        }
        vals.update(values)
        return self.env["ddfsc.employee.allowance"].create(vals)

    def test_allowance_approval_creates_one_effective_payroll_component(self):
        policy = self._allowance_policy()
        request = self._allowance_request(policy)
        request.action_submit()
        self.assertEqual(request.amount, 500.0)
        request.action_manager_approve()
        request.action_hr_approve()
        request.action_finance_approve()
        self.assertEqual(request.state, "approved")
        self.assertTrue(request.payroll_component_id)
        self.assertEqual(request.payroll_component_id.state, "approved")
        self.assertEqual(request.payroll_component_id.allowance_assignment_id, request)
        payslip = self._payslip()
        line = next(item for item in payslip.get_inputs(self.contract, payslip.date_from, payslip.date_to) if item["code"] == "TRANSPORT")
        self.assertEqual(line["amount"], 500.0)

    def test_allowance_policy_prevents_overlapping_approved_assignments(self):
        policy = self._allowance_policy()
        first = self._allowance_request(policy)
        first.action_submit(); first.action_manager_approve(); first.action_hr_approve(); first.action_finance_approve()
        second = self._allowance_request(policy, date_from=date(2026, 2, 1))
        second.action_submit(); second.action_manager_approve(); second.action_hr_approve()
        with self.assertRaises(UserError):
            second.action_finance_approve()

    def test_payroll_ineligible_employee_cannot_submit_or_receive_allowance(self):
        policy = self._allowance_policy()
        request = self._allowance_request(policy)
        self.employee.payroll_eligible = False
        with self.assertRaises(UserError):
            request.action_submit()

    def test_salary_revision_is_approved_applied_and_historized(self):
        grade = self.env["ddfsc.job.grade"].create({"name": "Skilled Operator", "code": "G6", "company_id": self.employee.company_id.id})
        self.env["ddfsc.salary.band"].create({
            "grade_id": grade.id, "minimum_salary": 4000, "midpoint_salary": 6000,
            "maximum_salary": 8000, "date_from": date(2026, 1, 1), "company_id": self.employee.company_id.id,
        })
        self.employee.ddfsc_job_grade_id = grade
        request = self.env["ddfsc.employee.change.request"].create({
            "request_type": "salary_revision", "reason_type": "performance", "employee_id": self.employee.id,
            "effective_date": date.today(), "justification": "Temporary test salary revision",
            "proposed_grade_id": grade.id, "proposed_basic_salary": 6000, "company_id": self.employee.company_id.id,
        })
        request.action_submit(); request.action_manager_approve(); request.action_hr_approve(); request.action_gm_approve()
        self.assertEqual(request.state, "applied")
        self.assertEqual(self.employee.version_id.wage, 6000)
        self.assertTrue(request.history_id)
        self.assertEqual(request.history_id.basic_salary, 6000)
        historical_payslip = self._payslip(1)
        current_payslip = self._payslip(date.today().month)
        self.assertEqual(historical_payslip.get_effective_basic_salary(self.contract), 5000)
        self.assertEqual(current_payslip.get_effective_basic_salary(self.contract), 6000)

    def test_loan_approval_and_disbursement_create_repayment_schedule(self):
        loan_type = self.env["ddfsc.loan.type"].create({
            "name": "Staff Emergency Loan", "code": "EMERGENCY", "maximum_months_basic": 3,
            "maximum_net_deduction_percent": 30, "maximum_term_months": 12,
            "company_id": self.employee.company_id.id,
        })
        loan = self.env["ddfsc.employee.loan"].create({
            "employee_id": self.employee.id, "loan_type_id": loan_type.id, "amount": 4500,
            "term_months": 3, "purpose": "Temporary test emergency expense",
            "company_id": self.employee.company_id.id,
        })
        loan.action_submit(); loan.action_manager_approve(); loan.action_hr_approve(); loan.action_finance_approve()
        loan.write({"disbursement_date": date(2026, 1, 1), "disbursement_reference": "TEST-DISB-001"})
        loan.action_disburse()
        self.assertEqual(loan.state, "disbursed")
        self.assertEqual(len(loan.repayment_ids), 3)
        self.assertEqual(sum(loan.repayment_ids.mapped("total_due")), 4500)
        self.assertTrue(loan.repayment_ids.mapped("component_id"))
        self.assertTrue(all(component.state == "approved" for component in loan.repayment_ids.mapped("component_id")))

    def test_completed_payslip_marks_linked_loan_repayment_paid(self):
        loan_type = self.env["ddfsc.loan.type"].create({
            "name": "Payroll Test Loan", "code": "PAYROLL_TEST", "maximum_months_basic": 3,
            "maximum_net_deduction_percent": 30, "maximum_term_months": 12,
            "company_id": self.employee.company_id.id,
        })
        loan = self.env["ddfsc.employee.loan"].create({
            "employee_id": self.employee.id, "loan_type_id": loan_type.id, "amount": 1500,
            "term_months": 1, "purpose": "Temporary payroll repayment test",
            "company_id": self.employee.company_id.id,
        })
        loan.action_submit(); loan.action_manager_approve(); loan.action_hr_approve(); loan.action_finance_approve()
        loan.write({"disbursement_date": date(2026, 1, 1), "disbursement_reference": "TEST-DISB-002"})
        loan.action_disburse()
        repayment = loan.repayment_ids
        payslip = self._payslip(2)
        payslip.write({"input_line_ids": [(0, 0, {
            "name": "Loan recovery", "code": "OTHER_DED", "amount": repayment.total_due,
            "contract_id": self.contract.id, "component_ids": [(6, 0, repayment.component_id.ids)],
        })]})
        payslip.with_context(without_compute_sheet=True).action_payslip_done()
        self.assertEqual(repayment.state, "paid")
        self.assertEqual(repayment.paid_payslip_id, payslip)
        self.assertEqual(loan.state, "closed")

    def test_early_settlement_cancels_future_payroll_deductions(self):
        loan_type = self.env["ddfsc.loan.type"].create({
            "name": "Settlement Test Loan", "code": "SETTLE_TEST", "maximum_months_basic": 3,
            "maximum_net_deduction_percent": 30, "maximum_term_months": 12,
            "company_id": self.employee.company_id.id,
        })
        loan = self.env["ddfsc.employee.loan"].create({
            "employee_id": self.employee.id, "loan_type_id": loan_type.id, "amount": 3000,
            "term_months": 2, "purpose": "Temporary settlement test", "company_id": self.employee.company_id.id,
        })
        loan.action_submit(); loan.action_manager_approve(); loan.action_hr_approve(); loan.action_finance_approve()
        loan.write({"disbursement_date": date(2026, 1, 1), "disbursement_reference": "TEST-DISB-003"})
        loan.action_disburse()
        loan.write({"settlement_amount": 3000, "settlement_date": date(2026, 1, 15), "settlement_reference": "CASH-SETTLE-001"})
        loan.action_early_settle()
        self.assertEqual(loan.state, "closed")
        self.assertTrue(all(line.state == "paid" for line in loan.repayment_ids))
        self.assertTrue(all(component.state == "cancelled" for component in loan.repayment_ids.mapped("component_id")))
