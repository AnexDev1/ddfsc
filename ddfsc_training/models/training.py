from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class TrainingCourse(models.Model):
    _name = "ddfsc.training.course"
    _description = "Training Course"
    name = fields.Char(required=True)
    category = fields.Char()
    provider = fields.Char()
    duration_hours = fields.Float(required=True, default=1)
    description = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)


class TrainingRequest(models.Model):
    _name = "ddfsc.training.request"
    _description = "Training Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "request_date desc, id desc"
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="restrict")
    course_id = fields.Many2one("ddfsc.training.course", required=True, ondelete="restrict")
    request_date = fields.Date(default=fields.Date.context_today, required=True)
    justification = fields.Text(required=True)
    expected_outcome = fields.Text()
    state = fields.Selection([("draft","Draft"),("manager","Pending Manager"),("hr","Pending HR"),("approved","Approved"),("rejected","Rejected"),("cancelled","Cancelled")], default="draft", tracking=True)
    company_id = fields.Many2one(related="employee_id.company_id", store=True, readonly=True)
    session_id = fields.Many2one("ddfsc.training.session", readonly=True)
    def action_submit(self): self.write({"state":"manager"})
    def action_manager_approve(self):
        for rec in self:
            if rec.state != "manager": raise UserError(_("This request is not awaiting manager approval."))
            if not (self.env.is_superuser() or rec.employee_id.parent_id.user_id == self.env.user or self.env.user.has_group("hr.group_hr_manager")):
                raise AccessError(_("Only the employee's manager or HR Manager can approve this step."))
        self.write({"state":"hr"})
    def action_hr_approve(self):
        if not (self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager")): raise AccessError(_("Only HR Manager can approve training."))
        self.write({"state":"approved"})
    def action_reject(self): self.write({"state":"rejected"})


class TrainingSession(models.Model):
    _name = "ddfsc.training.session"
    _description = "Training Session"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    name = fields.Char(required=True)
    course_id = fields.Many2one("ddfsc.training.course", required=True, ondelete="restrict")
    date_start = fields.Datetime(required=True)
    date_end = fields.Datetime(required=True)
    venue = fields.Char()
    trainer = fields.Char()
    capacity = fields.Integer(default=1)
    cost = fields.Monetary()
    currency_id = fields.Many2one(related="company_id.currency_id")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    state = fields.Selection([("draft","Draft"),("scheduled","Scheduled"),("completed","Completed"),("cancelled","Cancelled")], default="draft", tracking=True)
    attendee_ids = fields.One2many("ddfsc.training.attendee", "session_id")
    @api.constrains("date_start", "date_end", "capacity")
    def _check_session(self):
        if any(r.date_end <= r.date_start or r.capacity <= 0 for r in self): raise ValidationError(_("End must be after start and capacity must be positive."))
    def action_schedule(self): self.write({"state":"scheduled"})
    def action_complete(self): self.write({"state":"completed"})


class TrainingAttendee(models.Model):
    _name = "ddfsc.training.attendee"
    _description = "Training Attendee"
    _sql_constraints = [("training_session_employee_unique", "unique(session_id, employee_id)", "An employee can be enrolled only once per session.")]
    session_id = fields.Many2one("ddfsc.training.session", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="restrict")
    request_id = fields.Many2one("ddfsc.training.request", ondelete="restrict")
    attendance_state = fields.Selection([("enrolled","Enrolled"),("attended","Attended"),("absent","Absent"),("completed","Completed")], default="enrolled")
    assessment_score = fields.Float()
    certificate_reference = fields.Char()
    certificate_expiry = fields.Date()
    company_id = fields.Many2one(related="session_id.company_id", store=True)
    @api.constrains("assessment_score")
    def _check_score(self):
        if any(r.assessment_score < 0 or r.assessment_score > 100 for r in self): raise ValidationError(_("Assessment score must be between 0 and 100."))
    @api.constrains("session_id")
    def _check_capacity(self):
        for r in self:
            if len(r.session_id.attendee_ids) > r.session_id.capacity: raise ValidationError(_("Session capacity has been reached."))
