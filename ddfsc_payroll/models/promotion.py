from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DdfscJobGrade(models.Model):
    _name = "ddfsc.job.grade"
    _description = "Job Grade"
    _order = "sequence, code"
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    _code_company_unique = models.Constraint("unique(code, company_id)", "Job-grade code must be unique per company.")


class DdfscSalaryBand(models.Model):
    _name = "ddfsc.salary.band"
    _description = "Salary Band"
    _order = "date_from desc, grade_id"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    grade_id = fields.Many2one("ddfsc.job.grade", required=True, ondelete="restrict", check_company=True)
    minimum_salary = fields.Monetary(required=True)
    midpoint_salary = fields.Monetary(required=True)
    maximum_salary = fields.Monetary(required=True)
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date()
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text()

    @api.depends("grade_id", "date_from")
    def _compute_name(self):
        for band in self:
            band.name = "%s — %s" % (band.grade_id.display_name, band.date_from or "")

    @api.constrains("minimum_salary", "midpoint_salary", "maximum_salary", "date_from", "date_to")
    def _check_band(self):
        for band in self:
            if min(band.minimum_salary, band.midpoint_salary, band.maximum_salary) < 0:
                raise ValidationError(_("Salary-band values cannot be negative."))
            if not band.minimum_salary <= band.midpoint_salary <= band.maximum_salary:
                raise ValidationError(_("Salary band must satisfy minimum ≤ midpoint ≤ maximum."))
            if band.date_to and band.date_to < band.date_from:
                raise ValidationError(_("Salary-band end date cannot be before its effective date."))


class DdfscCompensationHistory(models.Model):
    _name = "ddfsc.compensation.history"
    _description = "Employee Compensation History"
    _order = "date_from desc, id desc"
    _check_company_auto = True

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True)
    request_id = fields.Many2one("ddfsc.employee.change.request", ondelete="restrict", index=True)
    basic_salary = fields.Monetary(required=True)
    date_from = fields.Date(required=True, index=True)
    date_to = fields.Date(index=True)
    grade_id = fields.Many2one("ddfsc.job.grade", check_company=True)
    job_id = fields.Many2one("hr.job", check_company=True)
    department_id = fields.Many2one("hr.department", check_company=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    note = fields.Char()

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        if any(record.date_to and record.date_to < record.date_from for record in self):
            raise ValidationError(_("Compensation-history end date cannot precede its effective date."))


class DdfscEmployeeChangeRequest(models.Model):
    _name = "ddfsc.employee.change.request"
    _description = "Promotion and Compensation Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "effective_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(readonly=True, copy=False, default=lambda self: _("New"), tracking=True)
    request_type = fields.Selection(
        [("promotion", "Promotion"), ("salary_revision", "Salary Revision"), ("transfer", "Transfer")],
        required=True, default="promotion", tracking=True,
    )
    reason_type = fields.Selection(
        [("performance", "Performance"), ("experience", "Experience"), ("qualification", "Qualification"), ("management", "Management Decision"), ("operational", "Operational Need")],
        required=True, default="management", tracking=True,
    )
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", tracking=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    effective_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    justification = fields.Text(required=True, tracking=True)

    current_job_id = fields.Many2one("hr.job", readonly=True, check_company=True)
    current_department_id = fields.Many2one("hr.department", readonly=True, check_company=True)
    current_manager_id = fields.Many2one("hr.employee", readonly=True, check_company=True)
    current_grade_id = fields.Many2one("ddfsc.job.grade", readonly=True, check_company=True)
    current_basic_salary = fields.Monetary(readonly=True)
    proposed_job_id = fields.Many2one("hr.job", check_company=True, tracking=True)
    proposed_department_id = fields.Many2one("hr.department", check_company=True, tracking=True)
    proposed_manager_id = fields.Many2one("hr.employee", check_company=True, tracking=True)
    proposed_grade_id = fields.Many2one("ddfsc.job.grade", check_company=True, tracking=True)
    proposed_basic_salary = fields.Monetary(tracking=True)

    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Pending Manager"), ("manager_approved", "Pending HR"), ("hr_approved", "Pending General Manager"), ("approved", "Approved — Awaiting Effective Date"), ("applied", "Applied"), ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="draft", required=True, tracking=True,
    )
    requested_by_id = fields.Many2one("res.users", readonly=True, default=lambda self: self.env.user)
    manager_approved_by_id = fields.Many2one("res.users", readonly=True)
    manager_approved_at = fields.Datetime(readonly=True)
    manager_note = fields.Text()
    hr_approved_by_id = fields.Many2one("res.users", readonly=True)
    hr_approved_at = fields.Datetime(readonly=True)
    hr_note = fields.Text()
    gm_approved_by_id = fields.Many2one("res.users", readonly=True)
    gm_approved_at = fields.Datetime(readonly=True)
    gm_note = fields.Text()
    rejection_reason = fields.Text(tracking=True)
    applied_at = fields.Datetime(readonly=True)
    applied_by_id = fields.Many2one("res.users", readonly=True)
    history_id = fields.Many2one("ddfsc.compensation.history", readonly=True, copy=False, ondelete="restrict")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("ddfsc.employee.change.request") or _("New")
            employee = self.env["hr.employee"].browse(vals.get("employee_id"))
            if employee:
                contract = employee.version_id
                vals.setdefault("company_id", employee.company_id.id)
                vals.setdefault("current_job_id", employee.job_id.id)
                vals.setdefault("current_department_id", employee.department_id.id)
                vals.setdefault("current_manager_id", employee.parent_id.id)
                vals.setdefault("current_grade_id", employee.ddfsc_job_grade_id.id)
                vals.setdefault("current_basic_salary", contract.wage if contract else 0.0)
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        for request in self:
            employee = request.employee_id
            if employee:
                contract = employee.version_id
                request.company_id = employee.company_id
                request.current_job_id = employee.job_id
                request.current_department_id = employee.department_id
                request.current_manager_id = employee.parent_id
                request.current_grade_id = employee.ddfsc_job_grade_id
                request.current_basic_salary = contract.wage if contract else 0.0

    @api.constrains("employee_id", "company_id", "proposed_basic_salary", "request_type")
    def _check_request_values(self):
        for request in self:
            if request.employee_id.company_id != request.company_id:
                raise ValidationError(_("Employee and request must belong to the same company."))
            if request.proposed_basic_salary < 0:
                raise ValidationError(_("Proposed salary cannot be negative."))
            if request.request_type == "salary_revision" and not request.proposed_basic_salary:
                raise ValidationError(_("A salary-revision request needs a proposed basic salary."))

    def _ensure_open(self):
        if self.state in ("approved", "applied", "cancelled"):
            raise UserError(_("This approved, applied, or cancelled request cannot follow that action."))

    def _require_manager_right(self):
        if self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager") or self.employee_id.parent_id.user_id == self.env.user:
            return
        raise AccessError(_("Only the employee's supervisor or an HR Manager can perform manager approval."))

    def action_submit(self):
        for request in self:
            if request.state not in ("draft", "rejected"):
                raise UserError(_("Only draft or rejected requests can be submitted."))
            request.write({"state": "submitted", "rejection_reason": False})
        return True

    def action_manager_approve(self):
        for request in self:
            request._require_manager_right()
            if request.state != "submitted":
                raise UserError(_("This request is not awaiting manager approval."))
            request.write({"state": "manager_approved", "manager_approved_by_id": self.env.user.id, "manager_approved_at": fields.Datetime.now()})
        return True

    def action_hr_approve(self):
        if not (self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager")):
            raise AccessError(_("Only an HR Manager can approve the HR step."))
        for request in self:
            if request.state != "manager_approved":
                raise UserError(_("This request is not awaiting HR approval."))
            request.write({"state": "hr_approved", "hr_approved_by_id": self.env.user.id, "hr_approved_at": fields.Datetime.now()})
        return True

    def action_gm_approve(self):
        if not (self.env.is_superuser() or self.env.user.has_group("ddfsc_manufacturing.group_ddfsc_gm")):
            raise AccessError(_("Only the General Manager can give final approval."))
        for request in self:
            if request.state != "hr_approved":
                raise UserError(_("This request is not awaiting General Manager approval."))
            request.write({"state": "approved", "gm_approved_by_id": self.env.user.id, "gm_approved_at": fields.Datetime.now()})
            if request.effective_date <= fields.Date.context_today(request):
                request.action_apply()
        return True

    def action_apply(self):
        for request in self:
            if request.state != "approved":
                raise UserError(_("Only finally approved requests can be applied."))
            if request.effective_date > fields.Date.context_today(request):
                raise UserError(_("This change cannot be applied before %(date)s.", date=request.effective_date))
            request._apply_change()
        return True

    @api.model
    def action_apply_due(self):
        due = self.search([("state", "=", "approved"), ("effective_date", "<=", fields.Date.context_today(self))])
        for request in due:
            request._apply_change()
        return True

    def _apply_change(self):
        self.ensure_one()
        employee = self.employee_id
        values = {}
        for field_name, proposed in (("job_id", self.proposed_job_id), ("department_id", self.proposed_department_id), ("parent_id", self.proposed_manager_id), ("ddfsc_job_grade_id", self.proposed_grade_id)):
            if proposed:
                values[field_name] = proposed.id
        if values:
            employee.write(values)
        if self.proposed_basic_salary and self.proposed_basic_salary != self.current_basic_salary:
            self._record_salary_history()
            employee.version_id.write({"wage": self.proposed_basic_salary})
        self.write({"state": "applied", "applied_at": fields.Datetime.now(), "applied_by_id": self.env.user.id})

    def _record_salary_history(self):
        self.ensure_one()
        History = self.env["ddfsc.compensation.history"]
        previous = History.search([
            ("employee_id", "=", self.employee_id.id), ("company_id", "=", self.company_id.id),
            ("date_from", "<", self.effective_date), "|", ("date_to", "=", False), ("date_to", ">=", self.effective_date),
        ], order="date_from desc", limit=1)
        if previous:
            previous.write({"date_to": self.effective_date - timedelta(days=1)})
        else:
            contract_start = fields.Date.to_date(self.employee_id.version_id.contract_date_start) if self.employee_id.version_id.contract_date_start else self.effective_date
            if contract_start < self.effective_date:
                History.create({"employee_id": self.employee_id.id, "basic_salary": self.current_basic_salary, "date_from": contract_start, "date_to": self.effective_date - timedelta(days=1), "grade_id": self.current_grade_id.id, "job_id": self.current_job_id.id, "department_id": self.current_department_id.id, "company_id": self.company_id.id, "note": _("Baseline recorded before %(request)s.", request=self.name)})
        history = History.create({"employee_id": self.employee_id.id, "request_id": self.id, "basic_salary": self.proposed_basic_salary, "date_from": self.effective_date, "grade_id": self.proposed_grade_id.id or self.current_grade_id.id, "job_id": self.proposed_job_id.id or self.current_job_id.id, "department_id": self.proposed_department_id.id or self.current_department_id.id, "company_id": self.company_id.id, "note": _("Applied from %(request)s.", request=self.name)})
        self.history_id = history

    def action_reject(self):
        for request in self:
            request._ensure_open()
            if request.state == "submitted":
                request._require_manager_right()
            elif not (self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager") or self.env.user.has_group("ddfsc_manufacturing.group_ddfsc_gm")):
                raise AccessError(_("Only HR or the General Manager can reject this request at this stage."))
            if not request.rejection_reason:
                raise UserError(_("Enter a rejection reason before rejecting the request."))
            request.write({"state": "rejected"})
        return True


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    ddfsc_job_grade_id = fields.Many2one("ddfsc.job.grade", string="Job Grade", check_company=True, tracking=True)
    ddfsc_compensation_history_ids = fields.One2many("ddfsc.compensation.history", "employee_id", string="Compensation History")
