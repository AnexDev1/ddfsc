"""Overtime paid by category, as Labour Proclamation 1156/2019 Art. 68 requires.

* 1.5 × the hourly wage for overtime between 06:00 and 22:00;
* 1.75 × for night overtime between 22:00 and 06:00;
* 2 × on the weekly rest day;
* 2.5 × on a public holiday.

Each approved overtime request is split into these categories from its
check-in / check-out times and the scheduled shift; the approved hours are
shared between the categories in the same proportion as the eligible hours.
"""

from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

NIGHT_START = 22
NIGHT_END = 6


def _night_seconds(start, stop, timezone):
    """Seconds of the UTC-naive interval [start, stop] falling in 22:00-06:00 local time."""
    if not start or not stop or stop <= start:
        return 0.0
    local_start = pytz.utc.localize(start).astimezone(timezone)
    local_stop = pytz.utc.localize(stop).astimezone(timezone)
    total = 0.0
    day = local_start.date() - timedelta(days=1)
    while day <= local_stop.date():
        night_from = timezone.localize(datetime.combine(day, time(NIGHT_START)))
        night_to = timezone.localize(datetime.combine(day + timedelta(days=1), time(NIGHT_END)))
        overlap = (min(local_stop, night_to) - max(local_start, night_from)).total_seconds()
        total += max(overlap, 0.0)
        day += timedelta(days=1)
    return total


class DdfscOvertimePayRate(models.Model):
    _inherit = "ddfsc.overtime.pay.rate"

    multiplier = fields.Float(string="Day Overtime Multiplier (06-22)")
    night_multiplier = fields.Float(string="Night Overtime Multiplier (22-06)", default=1.75, digits=(8, 4))
    rest_day_multiplier = fields.Float(string="Weekly Rest Day Multiplier", default=2.0, digits=(8, 4))
    holiday_multiplier = fields.Float(string="Public Holiday Multiplier", default=2.5, digits=(8, 4))

    @api.model
    def calculate_split_payment(self, hours, monthly_wage, payroll_date=None, company=None):
        """Pay a {category: hours} split; categories: day, night, rest_day, holiday."""
        company = company or self.env.company
        payroll_date = payroll_date or fields.Date.context_today(self)
        rate = self.search([
            ("company_id", "=", company.id), ("active", "=", True),
            ("date_from", "<=", payroll_date), "|", ("date_to", "=", False), ("date_to", ">=", payroll_date),
        ], order="date_from desc", limit=1)
        if not rate:
            # Same error as the single-rate calculation.
            return self.calculate_payment(sum(hours.values()), monthly_wage, payroll_date, company)
        hourly = max(float(monthly_wage or 0.0), 0.0) / rate.monthly_standard_hours
        multipliers = {
            "day": rate.multiplier, "night": rate.night_multiplier,
            "rest_day": rate.rest_day_multiplier, "holiday": rate.holiday_multiplier,
        }
        return round(sum(max(value, 0.0) * hourly * multipliers[key] for key, value in hours.items()), 2)


class DdfscOvertimeRequest(models.Model):
    _inherit = "ddfsc.overtime.request"

    ot_day_hours = fields.Float(string="Day Hours (1.5×)", compute="_compute_ot_split", store=True, digits=(16, 2))
    ot_night_hours = fields.Float(string="Night Hours (1.75×)", compute="_compute_ot_split", store=True, digits=(16, 2))
    ot_rest_day_hours = fields.Float(string="Rest Day Hours (2×)", compute="_compute_ot_split", store=True, digits=(16, 2))
    ot_holiday_hours = fields.Float(string="Holiday Hours (2.5×)", compute="_compute_ot_split", store=True, digits=(16, 2))

    def _ddfsc_is_public_holiday(self):
        self.ensure_one()
        company = self.employee_id.company_id
        if self.env["ddfsc.public.holiday"].sudo().is_non_working_day(company, self.work_date):
            return True
        timezone = pytz.timezone(self.employee_id._get_tz())
        noon = timezone.localize(datetime.combine(self.work_date, time(12))).astimezone(pytz.utc).replace(tzinfo=None)
        return bool(self.env["resource.calendar.leaves"].sudo().search_count([
            ("resource_id", "=", False), ("company_id", "in", (company.id, False)),
            ("date_from", "<=", noon), ("date_to", ">=", noon),
        ]))

    @api.depends("work_date", "employee_id", "scheduled_start", "scheduled_end", "first_check_in",
                 "last_check_out", "eligible_hours", "approved_hours", "attendance_ids")
    def _compute_ot_split(self):
        for request in self:
            hours = request.approved_hours or request.eligible_hours or 0.0
            split = {"day": 0.0, "night": 0.0, "rest_day": 0.0, "holiday": 0.0}
            if hours and request.employee_id and request.work_date:
                if request._ddfsc_is_public_holiday():
                    split["holiday"] = hours
                elif not request.scheduled_start:
                    split["rest_day"] = hours
                else:
                    timezone = pytz.timezone(request.employee_id._get_tz())
                    intervals = []
                    if request.first_check_in and request.first_check_in < request.scheduled_start:
                        intervals.append((request.first_check_in, request.scheduled_start))
                    if request.last_check_out and request.scheduled_end and request.last_check_out > request.scheduled_end:
                        intervals.append((request.scheduled_end, request.last_check_out))
                    total = sum((stop - start).total_seconds() for start, stop in intervals)
                    night = sum(_night_seconds(start, stop, timezone) for start, stop in intervals)
                    night_share = night / total if total else 0.0
                    split["night"] = round(hours * night_share, 2)
                    split["day"] = round(hours - split["night"], 2)
            request.ot_day_hours = split["day"]
            request.ot_night_hours = split["night"]
            request.ot_rest_day_hours = split["rest_day"]
            request.ot_holiday_hours = split["holiday"]

    def _ddfsc_hours_split(self):
        return {
            "day": sum(self.mapped("ot_day_hours")), "night": sum(self.mapped("ot_night_hours")),
            "rest_day": sum(self.mapped("ot_rest_day_hours")), "holiday": sum(self.mapped("ot_holiday_hours")),
        }
