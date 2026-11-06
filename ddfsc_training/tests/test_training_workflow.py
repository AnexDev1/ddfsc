from datetime import datetime, timedelta

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTrainingWorkflow(TransactionCase):
    def test_request_approval_and_session_capacity(self):
        employee = self.env["hr.employee"].create({"name": "Training Test Employee"})
        course = self.env["ddfsc.training.course"].create({"name": "Food Safety", "duration_hours": 8})
        request = self.env["ddfsc.training.request"].create({"employee_id": employee.id, "course_id": course.id, "justification": "Required for factory quality controls"})
        request.action_submit(); request.action_manager_approve(); request.action_hr_approve()
        self.assertEqual(request.state, "approved")
        start = datetime.now()
        session = self.env["ddfsc.training.session"].create({"name": "Food Safety 2026", "course_id": course.id, "date_start": start, "date_end": start + timedelta(hours=8), "capacity": 1})
        attendee = self.env["ddfsc.training.attendee"].create({"session_id": session.id, "employee_id": employee.id, "request_id": request.id})
        attendee.write({"attendance_state": "completed", "assessment_score": 86, "certificate_reference": "FS-2026-001"})
        self.assertEqual(attendee.attendance_state, "completed")
        second = self.env["hr.employee"].create({"name": "Second Trainee"})
        with self.assertRaises(ValidationError):
            self.env["ddfsc.training.attendee"].create({"session_id": session.id, "employee_id": second.id})
