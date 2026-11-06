from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class PerformanceCycle(models.Model):
    _name = "ddfsc.performance.cycle"
    _description = "Performance Evaluation Cycle"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_end desc, id desc"

    name = fields.Char(required=True, tracking=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    state = fields.Selection([("draft", "Draft"), ("open", "Open"), ("closed", "Closed")], default="draft", tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        if any(rec.date_end < rec.date_start for rec in self):
            raise ValidationError(_("Evaluation end date cannot be before start date."))

    def action_open(self): self.write({"state": "open"})
    def action_close(self): self.write({"state": "closed"})


class PerformanceTemplate(models.Model):
    _name = "ddfsc.performance.template"
    _description = "Performance Template"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    line_ids = fields.One2many("ddfsc.performance.template.line", "template_id", string="KPIs")

    @api.constrains("line_ids")
    def _check_weights(self):
        for rec in self:
            if rec.line_ids and sum(rec.line_ids.mapped("weight")) != 100:
                raise ValidationError(_("Template KPI weights must total exactly 100%."))


class PerformanceTemplateLine(models.Model):
    _name = "ddfsc.performance.template.line"
    _description = "Performance Template KPI"
    _order = "sequence, id"

    template_id = fields.Many2one("ddfsc.performance.template", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    description = fields.Text()
    weight = fields.Float(required=True, default=10)
    target = fields.Char()

    @api.constrains("weight")
    def _check_weight(self):
        if any(line.weight <= 0 or line.weight > 100 for line in self):
            raise ValidationError(_("Each KPI weight must be greater than 0 and no more than 100%."))


class PerformanceEvaluation(models.Model):
    _name = "ddfsc.performance.evaluation"
    _description = "Employee Performance Evaluation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "cycle_id desc, employee_id"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="restrict", tracking=True)
    cycle_id = fields.Many2one("ddfsc.performance.cycle", required=True, ondelete="restrict", tracking=True)
    template_id = fields.Many2one("ddfsc.performance.template", required=True, ondelete="restrict")
    manager_id = fields.Many2one(related="employee_id.parent_id", readonly=True)
    company_id = fields.Many2one(related="employee_id.company_id", store=True, readonly=True)
    state = fields.Selection([("draft", "Draft"), ("self_assessment", "Self Assessment"), ("supervisor_review", "Supervisor Review"), ("hr_review", "HR Review"), ("finalized", "Finalized")], default="draft", tracking=True)
    line_ids = fields.One2many("ddfsc.performance.evaluation.line", "evaluation_id", copy=True)
    self_comment = fields.Text()
    supervisor_comment = fields.Text()
    hr_comment = fields.Text()
    final_score = fields.Float(compute="_compute_score", store=True)
    rating = fields.Selection([("needs_improvement", "Needs Improvement"), ("meets", "Meets Expectations"), ("exceeds", "Exceeds Expectations"), ("outstanding", "Outstanding")], compute="_compute_score", store=True)
    _cycle_employee_unique = models.Constraint("unique(employee_id, cycle_id)", "An employee can have only one evaluation per cycle.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            template = self.env["ddfsc.performance.template"].browse(vals.get("template_id"))
            if template and not vals.get("line_ids"):
                vals["line_ids"] = [(0, 0, {"name": l.name, "description": l.description, "target": l.target, "weight": l.weight}) for l in template.line_ids]
        return super().create(vals_list)

    @api.depends("line_ids.weight", "line_ids.supervisor_score")
    def _compute_score(self):
        for rec in self:
            score = sum(line.weight * line.supervisor_score / 100 for line in rec.line_ids)
            rec.final_score = score
            rec.rating = "outstanding" if score >= 90 else "exceeds" if score >= 75 else "meets" if score >= 60 else "needs_improvement"

    def action_start(self):
        if any(rec.cycle_id.state != "open" for rec in self): raise UserError(_("The evaluation cycle must be open."))
        self.write({"state": "self_assessment"})

    def action_submit_self(self):
        for rec in self:
            if not (self.env.is_superuser() or rec.employee_id.user_id == self.env.user or self.env.user.has_group("hr.group_hr_manager")):
                raise AccessError(_("Only the evaluated employee or an HR Manager can submit self-assessment."))
        self.write({"state": "supervisor_review"})

    def action_submit_supervisor(self):
        for rec in self:
            if not (self.env.is_superuser() or rec.manager_id.user_id == self.env.user or self.env.user.has_group("hr.group_hr_manager")):
                raise AccessError(_("Only the employee's supervisor or an HR Manager can submit supervisor review."))
        self.write({"state": "hr_review"})

    def action_finalize(self):
        if not (self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager")):
            raise AccessError(_("Only an HR Manager can finalize an evaluation."))
        self.write({"state": "finalized"})

    def write(self, values):
        protected = {"employee_id", "cycle_id", "template_id", "line_ids"}
        if protected.intersection(values) and any(rec.state != "draft" for rec in self):
            raise UserError(_("Evaluation identity and KPI lines are locked once self-assessment starts."))
        return super().write(values)


class PerformanceEvaluationLine(models.Model):
    _name = "ddfsc.performance.evaluation.line"
    _description = "Performance Evaluation KPI"
    _order = "sequence, id"
    evaluation_id = fields.Many2one("ddfsc.performance.evaluation", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    description = fields.Text()
    target = fields.Char()
    weight = fields.Float(required=True)
    self_score = fields.Float()
    supervisor_score = fields.Float()
    self_comment = fields.Text()
    supervisor_comment = fields.Text()
    @api.constrains("self_score", "supervisor_score")
    def _check_scores(self):
        if any(score < 0 or score > 100 for rec in self for score in (rec.self_score, rec.supervisor_score)):
            raise ValidationError(_("Scores must be between 0 and 100."))


class PerformanceGoal(models.Model):
    _name = "ddfsc.performance.goal"
    _description = "Employee Performance Goal"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "cycle_id desc, employee_id"
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    cycle_id = fields.Many2one("ddfsc.performance.cycle", required=True, ondelete="restrict")
    name = fields.Char(required=True)
    target = fields.Text(required=True)
    weight = fields.Float(default=10)
    progress = fields.Float(default=0)
    state = fields.Selection([("draft", "Draft"), ("agreed", "Agreed"), ("completed", "Completed"), ("cancelled", "Cancelled")], default="draft", tracking=True)
    manager_comment = fields.Text()
    company_id = fields.Many2one(related="employee_id.company_id", store=True)
    @api.constrains("weight", "progress")
    def _check_values(self):
        if any(rec.weight <= 0 or rec.weight > 100 or rec.progress < 0 or rec.progress > 100 for rec in self):
            raise ValidationError(_("Goal weight and progress must be between 0 and 100."))
    def action_agree(self):
        for rec in self:
            if not (self.env.is_superuser() or rec.employee_id.parent_id.user_id == self.env.user or self.env.user.has_group("hr.group_hr_manager")):
                raise AccessError(_("Only the employee's supervisor or HR Manager can agree a goal."))
        self.write({"state": "agreed"})
    def action_complete(self): self.write({"state": "completed", "progress": 100})
