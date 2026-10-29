from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DdfscShiftAssignment(models.Model):
    _name = "ddfsc.shift.assignment"
    _description = "Employee Work Schedule Assignment"
    _inherit = ["mail.thread"]
    _order = "date_from desc, employee_id"

    employee_id = fields.Many2one(
        "hr.employee", required=True, ondelete="cascade", index=True, tracking=True
    )
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    calendar_id = fields.Many2one(
        "resource.calendar", string="Work Schedule", required=True, tracking=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    date_from = fields.Date(required=True, default=fields.Date.today, tracking=True)
    date_to = fields.Date(tracking=True)
    late_grace_minutes = fields.Integer(default=0, tracking=True)
    early_departure_grace_minutes = fields.Integer(default=0, tracking=True)
    notes = fields.Text()
    active = fields.Boolean(default=True)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for assignment in self:
            if assignment.date_to and assignment.date_to < assignment.date_from:
                raise ValidationError(_("Schedule end date cannot be before its start date."))

    @api.constrains("employee_id", "date_from", "date_to", "active")
    def _check_no_overlap(self):
        for assignment in self.filtered("active"):
            domain = [
                ("id", "!=", assignment.id),
                ("employee_id", "=", assignment.employee_id.id),
                ("active", "=", True),
                "|", ("date_to", "=", False), ("date_to", ">=", assignment.date_from),
            ]
            if assignment.date_to:
                domain.append(("date_from", "<=", assignment.date_to))
            if self.search_count(domain):
                raise ValidationError(_("Work schedule assignments for an employee cannot overlap."))
