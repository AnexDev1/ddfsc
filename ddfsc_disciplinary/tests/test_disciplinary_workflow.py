from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDisciplinaryWorkflow(TransactionCase):
    def test_case_workflow_and_closed_history_lock(self):
        employee = self.env["hr.employee"].create({"name": "Disciplinary Test Employee"})
        category = self.env["ddfsc.disciplinary.type"].create({"name": "Safety Procedure", "severity": "high"})
        case = self.env["ddfsc.disciplinary.case"].create({
            "employee_id": employee.id, "type_id": category.id, "reported_by": "Shift Supervisor",
            "description": "Temporary test incident record.",
        })
        self.assertNotEqual(case.name, "New")
        case.action_start_investigation(); case.findings = "Evidence reviewed"
        case.action_request_response(); case.employee_response = "Employee response recorded"
        case.action_schedule_hearing(); case.hearing_outcome = "Corrective coaching agreed"
        case.action_submit_decision(); case.action_type = "corrective"; case.action_close()
        self.assertEqual(case.state, "closed")
        with self.assertRaises(UserError):
            case.with_user(self.env.ref("base.user_admin")).write({"description": "Changed"})
