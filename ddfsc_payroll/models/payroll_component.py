import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class PayrollComponentType(models.Model):
    _name = "ddfsc.payroll.component.type"
    _description = "Payroll Component Type"
    _order = "component_kind, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, help="Short input code, for example TRANSPORT.")
    component_kind = fields.Selection(
        [("earning", "Earning"), ("deduction", "Deduction")], required=True, default="earning"
    )
    salary_rule_id = fields.Many2one(
        "hr.salary.rule", required=True, domain="[('company_id', 'in', [False, company_id])]",
        help="Rule that calculates this component. It should use inputs.CODE.amount.",
    )
    taxable = fields.Boolean(help="Classification only; the linked salary rule controls calculation.")
    pensionable = fields.Boolean(help="Classification only; the linked salary rule controls calculation.")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text()

    _code_unique = models.Constraint("unique(code, company_id)", "The component code must be unique per company.")

    @api.constrains("code")
    def _check_code(self):
        for record in self:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", record.code or ""):
                raise ValidationError(self.env._("Use uppercase letters, numbers, and underscores; start with a letter."))

    @api.constrains("salary_rule_id", "code")
    def _check_salary_rule_input(self):
        for record in self:
            if not record.salary_rule_id.input_ids.filtered(lambda item: item.code == record.code):
                raise ValidationError(self.env._(
                    "Salary rule '%(rule)s' must have an input with code '%(code)s'.",
                    rule=record.salary_rule_id.display_name, code=record.code,
                ))


class EmployeePayrollComponent(models.Model):
    _name = "ddfsc.employee.payroll.component"
    _description = "Employee Payroll Component"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="cascade", tracking=True)
    component_type_id = fields.Many2one(
        "ddfsc.payroll.component.type", required=True, ondelete="restrict",
        domain="[('company_id', '=', company_id)]", tracking=True,
    )
    component_kind = fields.Selection(related="component_type_id.component_kind", store=True)
    code = fields.Char(related="component_type_id.code", store=True)
    amount = fields.Monetary(required=True, tracking=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    recurrence = fields.Selection(
        [("recurring", "Recurring"), ("one_off", "One-time")], required=True, default="recurring", tracking=True,
    )
    date_from = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    date_to = fields.Date(tracking=True)
    state = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("cancelled", "Cancelled")],
        required=True, default="draft", tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    note = fields.Text()

    @api.constrains("amount")
    def _check_amount(self):
        if any(record.amount <= 0 for record in self):
            raise ValidationError(self.env._("The component amount must be greater than zero."))

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for record in self:
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(self.env._("End date cannot be earlier than start date."))

    @api.constrains("employee_id", "company_id")
    def _check_employee_company(self):
        for record in self:
            if record.employee_id.company_id != record.company_id:
                raise ValidationError(self.env._("Employee and component must belong to the same company."))

    def action_approve(self):
        self.filtered(lambda record: record.state == "draft").write({"state": "approved"})

    def action_reset_to_draft(self):
        self._raise_if_used_on_completed_payslip()
        self.write({"state": "draft"})

    def action_cancel(self):
        self._raise_if_used_on_completed_payslip()
        self.write({"state": "cancelled"})

    def _raise_if_used_on_completed_payslip(self):
        if self.env["hr.payslip.input"].search_count([
            ("component_ids", "in", self.ids), ("payslip_id.state", "=", "done")
        ]):
            raise UserError(self.env._("A component used by a completed payslip cannot be changed or cancelled."))

    def unlink(self):
        if any(record.state == "approved" for record in self):
            raise UserError(self.env._("Reset approved components to draft before deleting them."))
        return super().unlink()

    def write(self, vals):
        protected = {"employee_id", "component_type_id", "amount", "recurrence", "date_from", "date_to", "company_id"}
        approved = self.filtered(lambda record: record.state == "approved")
        if approved and protected.intersection(vals):
            raise UserError(self.env._("Reset approved components to draft before changing payroll values."))
        return super().write(vals)

