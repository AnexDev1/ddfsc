from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DdfscAllowancePolicy(models.Model):
    _name = "ddfsc.allowance.policy"
    _description = "Allowance Policy"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "active desc, name"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, tracking=True, help="Internal policy reference, for example TRANSPORT_FACTORY.")
    component_type_id = fields.Many2one(
        "ddfsc.payroll.component.type", required=True, ondelete="restrict", tracking=True,
        domain="[('component_kind', '=', 'earning'), ('company_id', '=', company_id), ('active', '=', True)]",
        help="The existing payroll component type used after Finance approval.",
    )
    calculation_method = fields.Selection(
        [("fixed", "Fixed Monthly Amount"), ("percentage_basic", "Percentage of Basic Salary")],
        required=True, default="fixed", tracking=True,
    )
    fixed_amount = fields.Monetary(tracking=True)
    percentage = fields.Float(string="Percentage of Basic Salary", digits=(7, 4), tracking=True)
    maximum_amount = fields.Monetary(
        help="Optional cap for a calculated allowance. Leave empty when no cap is approved.",
        tracking=True,
    )
    recurrence = fields.Selection(
        [("recurring", "Recurring Monthly"), ("one_off", "One-time")],
        required=True, default="recurring", tracking=True,
    )
    eligibility_scope = fields.Selection(
        [
            ("all", "All Eligible Employees"),
            ("department", "Selected Departments"),
            ("job", "Selected Job Positions"),
            ("employee", "Named Employees"),
        ],
        required=True, default="all", tracking=True,
    )
    department_ids = fields.Many2many("hr.department", string="Eligible Departments", check_company=True)
    job_ids = fields.Many2many("hr.job", string="Eligible Job Positions", check_company=True)
    employee_ids = fields.Many2many("hr.employee", string="Eligible Employees", check_company=True)
    date_from = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    date_to = fields.Date(tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    active = fields.Boolean(default=True, tracking=True)
    note = fields.Text(string="Policy Notes")

    _code_company_unique = models.Constraint(
        "unique(code, company_id)", "Allowance policy code must be unique per company."
    )

    @api.constrains("component_type_id")
    def _check_earning_component(self):
        if any(policy.component_type_id.component_kind != "earning" for policy in self):
            raise ValidationError(_("An allowance policy must use an earning component type."))

    @api.constrains("fixed_amount", "percentage", "maximum_amount", "calculation_method")
    def _check_amounts(self):
        for policy in self:
            if policy.fixed_amount < 0 or policy.percentage < 0 or policy.maximum_amount < 0:
                raise ValidationError(_("Allowance amounts and percentages cannot be negative."))
            if policy.calculation_method == "fixed" and policy.fixed_amount <= 0:
                raise ValidationError(_("Enter a fixed amount greater than zero."))
            if policy.calculation_method == "percentage_basic" and policy.percentage <= 0:
                raise ValidationError(_("Enter a percentage greater than zero."))

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        if any(policy.date_to and policy.date_to < policy.date_from for policy in self):
            raise ValidationError(_("Policy end date cannot be earlier than its effective date."))

    @api.constrains("eligibility_scope", "department_ids", "job_ids", "employee_ids")
    def _check_eligibility(self):
        requirements = {
            "department": "department_ids",
            "job": "job_ids",
            "employee": "employee_ids",
        }
        for policy in self:
            field_name = requirements.get(policy.eligibility_scope)
            if field_name and not policy[field_name]:
                raise ValidationError(_("Select at least one eligible record for the chosen eligibility scope."))

    def is_employee_eligible(self, employee, on_date=None):
        self.ensure_one()
        on_date = on_date or fields.Date.context_today(self)
        if not self.active or on_date < self.date_from or (self.date_to and on_date > self.date_to):
            return False
        if employee.company_id != self.company_id:
            return False
        if self.eligibility_scope == "all":
            return True
        if self.eligibility_scope == "department":
            return employee.department_id in self.department_ids
        if self.eligibility_scope == "job":
            return employee.job_id in self.job_ids
        return employee in self.employee_ids

    def calculate_amount(self, employee):
        self.ensure_one()
        if self.calculation_method == "fixed":
            amount = self.fixed_amount
        else:
            contract = employee.version_id
            if not contract or not contract.wage:
                raise UserError(_("Employee %(employee)s needs an active basic salary before this allowance can be calculated.", employee=employee.display_name))
            amount = contract.wage * self.percentage / 100.0
        return min(amount, self.maximum_amount) if self.maximum_amount else amount


class DdfscEmployeeAllowance(models.Model):
    _name = "ddfsc.employee.allowance"
    _description = "Employee Allowance Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"
    _check_company_auto = True

    name = fields.Char(readonly=True, copy=False, default=lambda self: _("New"), tracking=True)
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True, tracking=True)
    policy_id = fields.Many2one(
        "ddfsc.allowance.policy", required=True, ondelete="restrict", index=True, tracking=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    component_type_id = fields.Many2one(related="policy_id.component_type_id", store=True, readonly=True)
    calculation_method = fields.Selection(related="policy_id.calculation_method", readonly=True)
    amount = fields.Monetary(required=True, tracking=True, help="Approved monthly or one-time amount for this employee.")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    recurrence = fields.Selection(related="policy_id.recurrence", store=True, readonly=True)
    date_from = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    date_to = fields.Date(tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Pending Manager"),
            ("manager_approved", "Pending HR"),
            ("hr_approved", "Pending Finance"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        required=True, default="draft", tracking=True,
    )
    requested_by_id = fields.Many2one("res.users", readonly=True, copy=False, default=lambda self: self.env.user)
    submitted_at = fields.Datetime(readonly=True, copy=False)
    manager_approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    manager_approved_at = fields.Datetime(readonly=True, copy=False)
    manager_note = fields.Text()
    hr_approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    hr_approved_at = fields.Datetime(readonly=True, copy=False)
    hr_note = fields.Text()
    finance_approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    finance_approved_at = fields.Datetime(readonly=True, copy=False)
    finance_note = fields.Text()
    rejection_reason = fields.Text(copy=False, tracking=True)
    payroll_component_id = fields.Many2one("ddfsc.employee.payroll.component", readonly=True, copy=False, ondelete="restrict")
    payroll_component_count = fields.Integer(compute="_compute_payroll_component_count")
    note = fields.Text(string="Request Justification", tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("name", _("New")) == _("New"):
                values["name"] = self.env["ir.sequence"].next_by_code("ddfsc.employee.allowance") or _("New")
        return super().create(vals_list)

    @api.onchange("policy_id", "employee_id", "date_from")
    def _onchange_policy_or_employee(self):
        for allowance in self:
            if allowance.policy_id and allowance.employee_id:
                allowance.amount = allowance.policy_id.calculate_amount(allowance.employee_id)

    @api.constrains("employee_id", "policy_id", "company_id", "date_from", "date_to", "amount")
    def _check_request(self):
        for allowance in self:
            if allowance.amount <= 0:
                raise ValidationError(_("Allowance amount must be greater than zero."))
            if allowance.employee_id.company_id != allowance.company_id:
                raise ValidationError(_("Employee and allowance request must belong to the same company."))
            if allowance.policy_id.company_id != allowance.company_id:
                raise ValidationError(_("Allowance policy and request must belong to the same company."))
            if allowance.date_to and allowance.date_to < allowance.date_from:
                raise ValidationError(_("Allowance end date cannot be earlier than its effective date."))
            if allowance.policy_id.maximum_amount and allowance.amount > allowance.policy_id.maximum_amount:
                raise ValidationError(_("The requested amount exceeds the policy maximum."))

    def _check_policy_eligibility(self):
        for allowance in self:
            if not allowance.employee_id.active or not allowance.employee_id.payroll_eligible:
                raise UserError(_("An allowance cannot be approved for an inactive or payroll-ineligible employee."))
            if not allowance.policy_id.is_employee_eligible(allowance.employee_id, allowance.date_from):
                raise UserError(_("%(employee)s is not eligible for policy %(policy)s on %(date)s.", employee=allowance.employee_id.display_name, policy=allowance.policy_id.display_name, date=allowance.date_from))

    def _check_no_approved_overlap(self):
        for allowance in self:
            overlaps = self.search([
                ("id", "!=", allowance.id), ("employee_id", "=", allowance.employee_id.id),
                ("policy_id", "=", allowance.policy_id.id), ("state", "=", "approved"),
                ("date_from", "<=", allowance.date_to or fields.Date.today().replace(year=2099)),
                "|", ("date_to", "=", False), ("date_to", ">=", allowance.date_from),
            ], limit=1)
            if overlaps:
                raise UserError(_("An approved %(policy)s allowance already overlaps this employee's requested period: %(allowance)s.", policy=allowance.policy_id.display_name, allowance=overlaps.display_name))

    def _ensure_open(self):
        if any(allowance.state in ("approved", "cancelled") for allowance in self):
            raise UserError(_("Approved or cancelled allowance requests cannot be changed through this action."))

    def _is_employee_manager(self):
        self.ensure_one()
        return bool(self.employee_id.parent_id.user_id == self.env.user)

    def _require_manager_approval_right(self):
        if self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager") or self._is_employee_manager():
            return
        raise AccessError(_("Only the employee's supervisor or an HR Manager can approve the manager step."))

    def action_submit(self):
        for allowance in self:
            if allowance.state not in ("draft", "rejected"):
                raise UserError(_("Only draft or rejected requests can be submitted."))
            allowance._check_policy_eligibility()
            allowance.write({
                "amount": allowance.policy_id.calculate_amount(allowance.employee_id),
                "state": "submitted", "submitted_at": fields.Datetime.now(), "rejection_reason": False,
            })
        return True

    def action_manager_approve(self):
        for allowance in self:
            allowance._require_manager_approval_right()
            if allowance.state != "submitted":
                raise UserError(_("This request is not awaiting manager approval."))
            allowance.write({
                "state": "manager_approved", "manager_approved_by_id": self.env.user.id,
                "manager_approved_at": fields.Datetime.now(),
            })
        return True

    def action_hr_approve(self):
        if not (self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager")):
            raise AccessError(_("Only an HR Manager can approve the HR step."))
        for allowance in self:
            if allowance.state != "manager_approved":
                raise UserError(_("This request is not awaiting HR approval."))
            allowance.write({
                "state": "hr_approved", "hr_approved_by_id": self.env.user.id,
                "hr_approved_at": fields.Datetime.now(),
            })
        return True

    def action_finance_approve(self):
        if not (self.env.is_superuser() or self.env.user.has_group("payroll.group_payroll_manager")):
            raise AccessError(_("Only a Payroll/Finance Manager can approve the Finance step."))
        for allowance in self:
            if allowance.state != "hr_approved":
                raise UserError(_("This request is not awaiting Finance approval."))
            allowance._check_policy_eligibility()
            allowance._check_no_approved_overlap()
            allowance._create_payroll_component()
            allowance.write({
                "state": "approved", "finance_approved_by_id": self.env.user.id,
                "finance_approved_at": fields.Datetime.now(),
            })
        return True

    def _create_payroll_component(self):
        self.ensure_one()
        if self.payroll_component_id:
            return self.payroll_component_id
        component = self.env["ddfsc.employee.payroll.component"].create({
            "employee_id": self.employee_id.id,
            "component_type_id": self.component_type_id.id,
            "amount": self.amount,
            "recurrence": self.recurrence,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_id": self.company_id.id,
            "allowance_assignment_id": self.id,
            "note": _("Generated from approved allowance request %(reference)s.", reference=self.name),
            "state": "approved",
        })
        self.payroll_component_id = component
        return component

    def action_reject(self):
        for allowance in self:
            allowance._ensure_open()
            if allowance.state not in ("submitted", "manager_approved", "hr_approved"):
                raise UserError(_("Only submitted requests can be rejected."))
            if allowance.state == "submitted":
                allowance._require_manager_approval_right()
            elif not (self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager") or self.env.user.has_group("payroll.group_payroll_manager")):
                raise AccessError(_("Only HR or Finance can reject a request at this stage."))
            if not allowance.rejection_reason:
                raise UserError(_("Enter a rejection reason before rejecting the request."))
            allowance.write({"state": "rejected"})
        return True

    def action_cancel(self):
        for allowance in self:
            if allowance.state == "cancelled":
                continue
            if allowance.payroll_component_id:
                allowance.payroll_component_id.action_cancel()
            allowance.write({"state": "cancelled"})
        return True

    def action_reset_to_draft(self):
        for allowance in self:
            allowance._ensure_open()
            allowance.write({"state": "draft"})
        return True

    def _compute_payroll_component_count(self):
        for allowance in self:
            allowance.payroll_component_count = 1 if allowance.payroll_component_id else 0

    def action_open_payroll_component(self):
        self.ensure_one()
        if not self.payroll_component_id:
            return False
        return {
            "type": "ir.actions.act_window", "name": _("Payroll Component"),
            "res_model": "ddfsc.employee.payroll.component", "view_mode": "form",
            "res_id": self.payroll_component_id.id,
        }

    def write(self, values):
        protected = {"employee_id", "policy_id", "amount", "date_from", "date_to", "company_id"}
        if self.filtered(lambda allowance: allowance.state == "approved") and protected.intersection(values):
            raise UserError(_("Create a new dated allowance request instead of changing an approved allowance."))
        return super().write(values)
