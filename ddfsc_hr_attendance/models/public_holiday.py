from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models

DEFAULT_TZ = "Africa/Addis_Ababa"


class DdfscPublicHoliday(models.Model):
    """Company holiday calendar used by DDFSC attendance, time off and payroll.

    A factory closure is configured once for the company rather than entered as
    leave for every employee. Each non-working holiday is mirrored as an Odoo
    public holiday (a global ``resource.calendar.leaves``), so time-off
    durations, payroll worked days, overtime and attendance reviews all treat
    the day the same way.
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
    calendar_leave_id = fields.Many2one(
        "resource.calendar.leaves", string="Time Off Public Holiday", readonly=True, copy=False,
        ondelete="set null", help="The Odoo public holiday kept in step with this day.")

    _unique_holiday = models.Constraint(
        "unique(name, date, company_id)", "A holiday with this name already exists for this company and date."
    )

    @api.model
    def is_non_working_day(self, company, day):
        return bool(self.search_count([
            ("company_id", "=", company.id), ("date", "=", day),
            ("active", "=", True), ("non_working", "=", True),
        ]))

    def _calendar_leave_values(self):
        self.ensure_one()
        timezone = pytz.timezone(self.company_id.partner_id.tz or self.env.user.tz or DEFAULT_TZ)
        start = timezone.localize(datetime.combine(self.date, time.min))
        stop = start + timedelta(days=1) - timedelta(seconds=1)
        return {
            "name": self.name,
            "date_from": start.astimezone(pytz.utc).replace(tzinfo=None),
            "date_to": stop.astimezone(pytz.utc).replace(tzinfo=None),
            "company_id": self.company_id.id,
            "calendar_id": False,
            "resource_id": False,
            "time_type": "leave",
        }

    def _sync_calendar_leave(self):
        """Create, update or remove the mirrored Odoo public holiday."""
        Leaves = self.env["resource.calendar.leaves"].sudo()
        for holiday in self:
            wanted = holiday.active and holiday.non_working
            if wanted and holiday.calendar_leave_id:
                holiday.calendar_leave_id.sudo().write(holiday._calendar_leave_values())
            elif wanted:
                holiday.with_context(ddfsc_holiday_sync=True).calendar_leave_id = Leaves.create(
                    holiday._calendar_leave_values())
            elif holiday.calendar_leave_id:
                leave = holiday.calendar_leave_id
                holiday.with_context(ddfsc_holiday_sync=True).calendar_leave_id = False
                leave.sudo().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        holidays = super().create(vals_list)
        holidays._sync_calendar_leave()
        return holidays

    def write(self, values):
        result = super().write(values)
        if not self.env.context.get("ddfsc_holiday_sync") and \
                {"name", "date", "company_id", "non_working", "active"}.intersection(values):
            self._sync_calendar_leave()
        return result

    def unlink(self):
        leaves = self.mapped("calendar_leave_id")
        result = super().unlink()
        leaves.sudo().unlink()
        return result

    @api.model
    def _sync_existing_holidays(self):
        """Mirror holidays entered before the sync existed (runs on upgrade)."""
        self.with_context(active_test=False).search([("calendar_leave_id", "=", False)])._sync_calendar_leave()
        return True
