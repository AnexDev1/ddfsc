"""Tax-exempt allowance limit and payroll eligibility.

* Non-taxable cash allowances (e.g. transport) are exempt only up to a limit;
  the excess is taxable income. The limit is effective-dated and editable by
  the Payroll Manager.
* An employee who is not payroll-eligible cannot be paid, except for the final
  payslip of the period in which they leave (final settlement).
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DdfscNontaxableAllowanceLimit(models.Model):
    _name = "ddfsc.nontaxable.allowance.limit"
    _description = "Tax-exempt Allowance Limit"
    _order = "date_from desc"

    name = fields.Char(required=True, default="Transport allowance exemption")
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date()
    percent_of_basic = fields.Float(string="Exempt up to % of Basic", default=25.0, digits=(5, 2))
    maximum_amount = fields.Monetary(string="Exempt up to (monthly)", default=2200.0)
    currency_id = fields.Many2one(related="company_id.currency_id")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text(default="Confirm the exemption limit with DDFSC Finance and the current tax regulation before production use.")

    @api.constrains("percent_of_basic", "maximum_amount", "date_from", "date_to")
    def _check_values(self):
        for record in self:
            if not 0 <= record.percent_of_basic <= 100 or record.maximum_amount < 0:
                raise ValidationError(_("The exemption percentage must be 0-100 and the maximum cannot be negative."))
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(_("The end date cannot be before the effective date."))

    @api.model
    def exempt_amount(self, allowance, basic, payroll_date=None, company=None):
        """Part of ``allowance`` that is tax-exempt. Without a limit, all of it."""
        company = company or self.env.company
        payroll_date = payroll_date or fields.Date.context_today(self)
        limit = self.search([
            ("company_id", "=", company.id), ("active", "=", True), ("date_from", "<=", payroll_date),
            "|", ("date_to", "=", False), ("date_to", ">=", payroll_date),
        ], order="date_from desc", limit=1)
        allowance = max(float(allowance or 0.0), 0.0)
        if not limit:
            return allowance
        cap = min(max(float(basic or 0.0), 0.0) * limit.percent_of_basic / 100.0, limit.maximum_amount)
        return min(allowance, cap)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def get_exempt_allowance(self, allowance, basic):
        """Salary-rule helper: tax-exempt part of the non-taxable allowance input."""
        self.ensure_one()
        return self.env["ddfsc.nontaxable.allowance.limit"].exempt_amount(
            allowance, basic, self.date_to or self.date_from, self.company_id)

    def _ddfsc_payroll_allowed(self):
        """Eligible employees, or the final payslip covering an employee's departure."""
        self.ensure_one()
        employee = self.employee_id.sudo()
        if employee.payroll_eligible:
            return True
        return bool(employee.departure_date and self.date_from and employee.departure_date >= self.date_from)

    def compute_sheet(self):
        blocked = self.filtered(lambda payslip: payslip.employee_id and not payslip._ddfsc_payroll_allowed())
        if blocked:
            raise UserError(_(
                "These employees are not payroll-eligible for this period: %s. "
                "Only the final payslip of the period in which an employee leaves can be calculated.",
            ) % ", ".join(blocked.mapped("employee_id.name")))
        return super().compute_sheet()


class HrPayslipEmployees(models.TransientModel):
    _inherit = "hr.payslip.employees"

    def compute_sheet(self):
        """Leave out employees who may not be paid for the batch period."""
        run = self.env["hr.payslip.run"].browse(self.env.context.get("active_id"))
        if run:
            allowed = self.employee_ids.filtered(
                lambda employee: employee.sudo().payroll_eligible or (
                    employee.sudo().departure_date and employee.sudo().departure_date >= run.date_start))
            if not allowed:
                raise UserError(_("None of the selected employees is payroll-eligible for this period."))
            self.employee_ids = allowed
        return super().compute_sheet()
