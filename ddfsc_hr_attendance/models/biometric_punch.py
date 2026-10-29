import hashlib

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DdfscBiometricPunch(models.Model):
    _name = "ddfsc.biometric.punch"
    _description = "Raw Biometric Punch"
    _order = "event_time desc, id desc"
    _rec_name = "event_key"

    device_id = fields.Many2one(
        "ddfsc.biometric.device", required=True, ondelete="restrict", index=True
    )
    company_id = fields.Many2one(related="device_id.company_id", store=True, index=True)
    device_user_id = fields.Char(string="Device User ID", required=True, index=True)
    employee_id = fields.Many2one("hr.employee", readonly=True, index=True)
    event_time = fields.Datetime(required=True, index=True)
    punch_type = fields.Selection(
        [("in", "Check In"), ("out", "Check Out"), ("unknown", "Auto Detect")],
        required=True,
        default="unknown",
    )
    event_key = fields.Char(required=True, readonly=True, copy=False, index=True)
    state = fields.Selection(
        [
            ("new", "Ready to Process"),
            ("processed", "Processed"),
            ("unmapped", "Employee Not Mapped"),
            ("error", "Needs Review"),
            ("ignored", "Ignored"),
        ],
        required=True,
        default="new",
        readonly=True,
        index=True,
    )
    attendance_id = fields.Many2one("hr.attendance", readonly=True, copy=False)
    error_message = fields.Text(readonly=True, copy=False)
    imported_at = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    raw_payload = fields.Text(readonly=True, copy=False)

    _event_key_unique = models.Constraint(
        "UNIQUE(event_key)", "This biometric punch has already been imported."
    )

    @api.model
    def _make_event_key(self, device, device_user_id, event_time, punch_type):
        value = "%s|%s|%s|%s" % (
            device.code,
            str(device_user_id).strip(),
            fields.Datetime.to_string(event_time),
            punch_type,
        )
        return hashlib.sha256(value.encode()).hexdigest()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            device = self.env["ddfsc.biometric.device"].browse(vals["device_id"])
            user_id = str(vals.get("device_user_id", "")).strip()
            event_time = fields.Datetime.to_datetime(vals["event_time"])
            punch_type = vals.get("punch_type", "unknown")
            vals["device_user_id"] = user_id
            vals["event_key"] = vals.get("event_key") or self._make_event_key(
                device, user_id, event_time, punch_type
            )
            employee = self.env["hr.employee"].search(
                [
                    ("biometric_user_id", "=", user_id),
                    ("company_id", "=", device.company_id.id),
                ],
                limit=1,
            )
            vals["employee_id"] = employee.id or False
            if not employee:
                vals["state"] = "unmapped"
                vals["error_message"] = _(
                    "No employee uses biometric ID %s in this company.", user_id
                )
        return super().create(vals_list)

    def write(self, vals):
        immutable = {"device_id", "device_user_id", "event_time", "punch_type", "event_key", "raw_payload"}
        if immutable.intersection(vals):
            raise ValidationError(_("Raw punch source data is immutable. Import a corrected event instead."))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get("module_uninstall"):
            raise UserError(_("Raw biometric punches are audit records and cannot be deleted."))
        return super().unlink()

    def action_retry_mapping(self):
        for punch in self.filtered(lambda item: item.state in ("unmapped", "error")):
            employee = self.env["hr.employee"].search(
                [
                    ("biometric_user_id", "=", punch.device_user_id),
                    ("company_id", "=", punch.company_id.id),
                ],
                limit=1,
            )
            punch.write(
                {
                    "employee_id": employee.id or False,
                    "state": "new" if employee else "unmapped",
                    "error_message": False if employee else _("Employee mapping is still missing."),
                }
            )
        return True

    def action_ignore(self):
        self.filtered(lambda item: item.state != "processed").write(
            {"state": "ignored", "error_message": False}
        )

    def action_process(self):
        for punch in self.sorted("event_time"):
            if punch.state in ("processed", "ignored"):
                continue
            if not punch.employee_id:
                punch.action_retry_mapping()
            if not punch.employee_id:
                continue
            try:
                punch._process_one()
            except (UserError, ValidationError) as error:
                punch.write({"state": "error", "error_message": str(error)})
        return True

    def _process_one(self):
        self.ensure_one()
        Attendance = self.env["hr.attendance"]
        open_attendance = Attendance.search(
            [("employee_id", "=", self.employee_id.id), ("check_out", "=", False)],
            order="check_in desc",
            limit=1,
        )
        effective_type = self.punch_type
        if effective_type == "unknown":
            effective_type = "out" if open_attendance else "in"

        if effective_type == "in":
            if open_attendance:
                raise ValidationError(
                    _("An open attendance already exists from %s.", open_attendance.check_in)
                )
            attendance = Attendance.create(
                {
                    "employee_id": self.employee_id.id,
                    "check_in": self.event_time,
                    "source": "biometric",
                    "check_in_punch_id": self.id,
                }
            )
        else:
            if not open_attendance:
                raise ValidationError(_("No earlier open check-in was found for this check-out."))
            if self.event_time < open_attendance.check_in:
                raise ValidationError(_("Check-out time is earlier than the open check-in."))
            open_attendance.with_context(biometric_processing=True).write(
                {"check_out": self.event_time, "check_out_punch_id": self.id, "source": "biometric"}
            )
            attendance = open_attendance
        self.write({"state": "processed", "attendance_id": attendance.id, "error_message": False})
