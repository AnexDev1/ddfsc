from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    payroll_component_ids = fields.One2many(
        "ddfsc.employee.payroll.component", "employee_id", string="Payroll Components"
    )

