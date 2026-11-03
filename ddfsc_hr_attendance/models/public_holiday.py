from odoo import api, fields, models
class DdfscPublicHoliday(models.Model):
    """Company holiday calendar used by DDFSC attendance reviews.

    This is intentionally separate from leave allocations: a factory closure is
    configured once for the company rather than entered as leave for every
    employee.
    """

    _name = "ddfsc.public.holiday"
    _description = "Public Holiday"
    _order = "date desc, name"

    name = fields.Char(required=True)
    date = fields.Date(required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    non_working = fields.Boolean(default=True, help="Do not create absence, late-arrival, or early-departure exceptions on this day.")
    note = fields.Text()
    active = fields.Boolean(default=True)

    _unique_holiday = models.Constraint(
        "unique(name, date, company_id)", "A holiday with this name already exists for this company and date."
    )

    @api.model
    def is_non_working_day(self, company, day):
        return bool(self.search_count([
            ("company_id", "=", company.id), ("date", "=", day),
            ("active", "=", True), ("non_working", "=", True),
        ]))
