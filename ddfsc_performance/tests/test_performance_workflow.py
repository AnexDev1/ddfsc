from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPerformanceWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["hr.employee"].create({"name": "Performance Test Manager"})
        cls.employee = cls.env["hr.employee"].create({"name": "Performance Test Employee", "parent_id": cls.manager.id})
        cls.cycle = cls.env["ddfsc.performance.cycle"].create({"name": "2026 Annual", "date_start": date(2026, 1, 1), "date_end": date(2026, 12, 31)})
        cls.template = cls.env["ddfsc.performance.template"].create({"name": "Factory Operator", "line_ids": [
            (0, 0, {"name": "Quality", "weight": 60, "target": "Pass all assigned quality checks"}),
            (0, 0, {"name": "Attendance", "weight": 40, "target": "Meet shift attendance target"}),
        ]})

    def test_weighted_score_and_finalization(self):
        self.cycle.action_open()
        evaluation = self.env["ddfsc.performance.evaluation"].create({"employee_id": self.employee.id, "cycle_id": self.cycle.id, "template_id": self.template.id})
        evaluation.action_start()
        evaluation.line_ids[0].self_score = 90
        evaluation.line_ids[1].self_score = 80
        evaluation.action_submit_self()
        evaluation.line_ids[0].supervisor_score = 90
        evaluation.line_ids[1].supervisor_score = 80
        evaluation.action_submit_supervisor()
        evaluation.action_finalize()
        self.assertEqual(evaluation.state, "finalized")
        self.assertEqual(evaluation.final_score, 86)
        self.assertEqual(evaluation.rating, "exceeds")
        with self.assertRaises(UserError):
            evaluation.write({"template_id": self.template.id})

    def test_cycle_must_be_open(self):
        evaluation = self.env["ddfsc.performance.evaluation"].create({"employee_id": self.employee.id, "cycle_id": self.cycle.id, "template_id": self.template.id})
        with self.assertRaises(UserError):
            evaluation.action_start()

    def test_goal_agreement_and_completion(self):
        goal = self.env["ddfsc.performance.goal"].create({
            "employee_id": self.employee.id, "cycle_id": self.cycle.id,
            "name": "Reduce flour production waste", "target": "Keep waste below agreed threshold", "weight": 25,
        })
        goal.action_agree()
        goal.action_complete()
        self.assertEqual(goal.state, "completed")
        self.assertEqual(goal.progress, 100)
