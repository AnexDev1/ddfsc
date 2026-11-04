from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DdfscAttendanceCorrection(models.Model):
    _name = "ddfsc.attendance.correction"
    _description = "Attendance Correction Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    attendance_id = fields.Many2one("hr.attendance", required=True, ondelete="restrict", tracking=True)
    employee_id = fields.Many2one(related="attendance_id.employee_id", store=True)
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    original_check_in = fields.Datetime(required=True, readonly=True)
    original_check_out = fields.Datetime(readonly=True)
    requested_check_in = fields.Datetime(tracking=True)
    requested_check_out = fields.Datetime(tracking=True)
    reason = fields.Text(required=True, tracking=True)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"),
         ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True, index=True,
    )
    requested_by = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, readonly=True)
    reviewed_by = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    review_note = fields.Text(tracking=True)

    @api.onchange("attendance_id")
    def _onchange_attendance_id(self):
        if self.attendance_id:
            self.original_check_in = self.attendance_id.check_in
            self.original_check_out = self.attendance_id.check_out
            self.requested_check_in = self.attendance_id.check_in
            self.requested_check_out = self.attendance_id.check_out

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            attendance = self.env["hr.attendance"].browse(vals.get("attendance_id"))
            if attendance:
                vals.setdefault("original_check_in", attendance.check_in)
                vals.setdefault("original_check_out", attendance.check_out)
        return super().create(vals_list)

    def action_submit(self):
        for request in self.filtered(lambda item: item.state == "draft"):
            check_in = request.requested_check_in or request.original_check_in
            check_out = request.requested_check_out or request.original_check_out
            if check_out and check_out < check_in:
                raise ValidationError(_("Requested check-out cannot be before check-in."))
            if check_in == request.original_check_in and check_out == request.original_check_out:
                raise ValidationError(_("Change at least one attendance time before submitting."))
            request.state = "submitted"
        return True

    def action_approve(self):
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise ValidationError(_("Only an Attendance Administrator can approve corrections."))
        for request in self.filtered(lambda item: item.state == "submitted"):
            values = {"correction_reason": request.reason}
            if request.requested_check_in:
                values["check_in"] = request.requested_check_in
            if request.requested_check_out:
                values["check_out"] = request.requested_check_out
            request.attendance_id.with_context(biometric_processing=True).write(values)
            request.write({"state": "approved", "reviewed_by": self.env.user.id,
                           "reviewed_at": fields.Datetime.now()})
        return True

    def action_reject(self):
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise ValidationError(_("Only an Attendance Administrator can reject corrections."))
        self.filtered(lambda item: item.state == "submitted").write(
            {"state": "rejected", "reviewed_by": self.env.user.id,
             "reviewed_at": fields.Datetime.now()}
        )

    def action_cancel(self):
        self.filtered(lambda item: item.state in ("draft", "submitted")).state = "cancelled"
