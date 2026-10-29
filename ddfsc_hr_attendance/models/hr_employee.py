from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    biometric_user_id = fields.Char(
        string="Biometric User ID",
        copy=False,
        index=True,
        tracking=True,
        help="Employee identifier stored on the attendance device.",
    )
    payroll_eligible = fields.Boolean(
        default=True,
        tracking=True,
        groups="hr.group_hr_user",
        help="Controls whether the employee may be included in future payroll processing.",
    )
    shift_assignment_ids = fields.One2many(
        "ddfsc.shift.assignment", "employee_id", string="Schedule History"
    )

    _biometric_user_company_unique = models.Constraint(
        "UNIQUE(biometric_user_id, company_id)",
        "Biometric User ID must be unique per company.",
    )
    employee_number = fields.Char(
        string="Employee Number", copy=False, index=True, tracking=True,
    )
    _employee_number_company_unique = models.Constraint(
        "UNIQUE(employee_number, company_id)",
        "Employee Number must be unique per company.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("employee_number", _("New")) == _("New"):
                vals["employee_number"] = self.env["ir.sequence"].next_by_code(
                    "ddfsc.hr.employee"
                ) or _("New")
        return super().create(vals_list)

    @api.constrains("departure_date", "contract_date_start")
    def _check_termination_date(self):
        for employee in self:
            if (
                employee.departure_date
                and employee.contract_date_start
                and employee.departure_date < employee.contract_date_start
            ):
                raise ValidationError(_("Termination date cannot be before the contract start date."))

    def action_terminate_employment(self):
        for employee in self:
            if not employee.departure_date:
                raise ValidationError(_("Enter a termination date before terminating employment."))
            employee.write({"payroll_eligible": False, "active": False})
        return True
