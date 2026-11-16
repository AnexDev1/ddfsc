"""Time off and employment dates in the Ethiopian basic salary.

The BASIC rule pays the salary in force for the working days the employee was
employed in the period, and reduces it for time off that is not fully paid
(e.g. unpaid leave, the 50 % and 0 % tiers of long sick leave under
Proclamation 1156/2019). Public holidays are paid days.
"""

from datetime import datetime, time

from pytz import timezone

from odoo import api, fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    ddfsc_pay_percent = fields.Float(
        string="Salary Paid %", default=100.0,
        help="Share of the basic salary paid for a day of this time off: 100 for paid leave, "
             "50 for half-paid sick leave, 0 for unpaid leave.")

    @api.model
    def _ddfsc_sync_unpaid_types(self):
        """Unpaid types start at 0 % (runs on upgrade; only types still at the default)."""
        self.with_context(active_test=False).search([
            ("unpaid", "=", True), ("ddfsc_pay_percent", "=", 100.0),
        ]).write({"ddfsc_pay_percent": 0.0})
        return True


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    ddfsc_paid_ratio = fields.Float(
        string="Paid Share of Month", compute="_compute_ddfsc_paid_ratio", digits=(16, 4),
        help="Working days paid ÷ working days in the period: employment dates and time off "
             "that is not fully paid reduce it.")

    @api.depends("date_from", "date_to", "contract_id", "employee_id")
    def _compute_ddfsc_paid_ratio(self):
        for payslip in self:
            payslip.ddfsc_paid_ratio = payslip._ddfsc_paid_ratio(payslip.contract_id) \
                if payslip.contract_id else 1.0

    def get_period_basic_salary(self, contract):
        """BASIC rule helper: salary in force × paid share of the period."""
        self.ensure_one()
        return self.get_effective_basic_salary(contract) * self._ddfsc_paid_ratio(contract)

    def _ddfsc_paid_ratio(self, contract):
        self.ensure_one()
        employee = contract.employee_id
        calendar = contract.resource_calendar_id or employee.resource_calendar_id
        if not (calendar and self.date_from and self.date_to and employee):
            return 1.0
        tz = timezone(calendar.tz or employee.tz or "UTC")

        def work_days(day_from, day_to):
            data = employee._get_work_days_data_batch(
                tz.localize(datetime.combine(day_from, time.min)),
                tz.localize(datetime.combine(day_to, time.max)),
                compute_leaves=False, calendar=calendar)
            return data.get(employee.id, {}).get("days", 0.0)

        total = work_days(self.date_from, self.date_to)
        if not total:
            return 1.0
        # Odoo 19 keeps the contract on the employee version (hr.version).
        contract_start = contract.contract_date_start if "contract_date_start" in contract._fields else contract.date_start
        contract_end = contract.contract_date_end if "contract_date_end" in contract._fields else contract.date_end
        start = max(self.date_from, contract_start or self.date_from)
        end = min([self.date_to] + [day for day in (contract_end, employee.departure_date) if day])
        if end < start:
            return 0.0
        employed = total if (start, end) == (self.date_from, self.date_to) else work_days(start, end)
        lost = 0.0
        for day, hours, leave in employee.list_leaves(
                tz.localize(datetime.combine(start, time.min)),
                tz.localize(datetime.combine(end, time.max)), calendar=calendar):
            leave_type = leave[:1].holiday_id.holiday_status_id
            if not leave_type:
                continue  # public holidays and company closures are paid
            unpaid_share = 1.0 - min(max(leave_type.ddfsc_pay_percent, 0.0), 100.0) / 100.0
            if not unpaid_share:
                continue
            day_hours = calendar.get_work_hours_count(
                tz.localize(datetime.combine(day, time.min)),
                tz.localize(datetime.combine(day, time.max)), compute_leaves=False)
            if day_hours:
                lost += hours / day_hours * unpaid_share
        return max(employed - lost, 0.0) / total
