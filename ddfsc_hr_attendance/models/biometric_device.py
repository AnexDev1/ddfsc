import json
import logging
from datetime import timedelta

import pytz

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DdfscBiometricDevice(models.Model):
    _name = "ddfsc.biometric.device"
    _description = "Biometric Attendance Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, copy=False, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    location = fields.Char(tracking=True)
    device_type = fields.Selection(
        [("zk", "ZKTeco / ZK protocol"), ("file", "File import"), ("other", "Other")],
        required=True,
        default="file",
        tracking=True,
    )
    ip_address = fields.Char(string="IP Address")
    port = fields.Integer(default=4370)
    password = fields.Integer(
        string="Device Communication Password",
        default=0,
        groups="hr_attendance.group_hr_attendance_manager",
    )
    protocol = fields.Selection(
        [("tcp", "TCP"), ("udp", "UDP")], default="tcp", required=True
    )
    use_device_punch_type = fields.Boolean(
        string="Use Device Check-in / Check-out Codes",
        default=False,
        help="Enable only when the device is configured to distinguish check-in and check-out. Otherwise scans alternate automatically.",
    )
    timezone = fields.Selection(
        selection=lambda self: self._tz_get(),
        default=lambda self: self.env.user.tz or "Africa/Addis_Ababa",
        required=True,
    )
    last_sync_at = fields.Datetime(readonly=True, copy=False)
    last_sync_status = fields.Selection(
        [("success", "Success"), ("failed", "Failed")], readonly=True, copy=False
    )
    last_sync_error = fields.Text(readonly=True, copy=False)
    auto_sync = fields.Boolean(string="Automatic Download", default=False, tracking=True)
    sync_interval_minutes = fields.Integer(default=30, tracking=True)
    next_sync_at = fields.Datetime(copy=False)
    notes = fields.Text()

    _code_company_unique = models.Constraint(
        "UNIQUE(code, company_id)", "Device code must be unique per company."
    )

    def _tz_get(self):
        return [(tz, tz) for tz in __import__("pytz").all_timezones]

    def _get_zk_connection(self):
        self.ensure_one()
        if self.device_type != "zk":
            raise UserError(_("This action is available only for ZKTeco devices."))
        if not self.ip_address:
            raise UserError(_("Enter the device IP address first."))
        try:
            from zk import ZK
        except ImportError as error:
            raise UserError(_("The pyzk library is not installed in the Odoo image.")) from error
        zk = ZK(
            self.ip_address,
            port=self.port or 4370,
            timeout=15,
            password=self.password or 0,
            force_udp=self.protocol == "udp",
            ommit_ping=True,
        )
        return zk.connect()

    def action_test_connection(self):
        self.ensure_one()
        connection = None
        try:
            connection = self._get_zk_connection()
            firmware = connection.get_firmware_version() or _("Unknown")
        except Exception as error:
            _logger.exception("ZKTeco connection test failed for %s", self.display_name)
            raise UserError(_("Could not connect to %(device)s: %(error)s", device=self.display_name, error=error)) from error
        finally:
            if connection:
                connection.disconnect()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Connection successful"),
                "message": _("ZKTeco firmware: %s", firmware),
                "type": "success",
                "sticky": False,
            },
        }

    def action_download_punches(self):
        self.ensure_one()
        created, duplicates = self._download_punches(trigger="manual")
        return {
            "type": "ir.actions.act_window",
            "name": _("Downloaded Punches (%(new)s new, %(duplicate)s duplicates)", new=len(created), duplicate=duplicates),
            "res_model": "ddfsc.biometric.punch",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
        }

    def _download_punches(self, trigger="scheduled"):
        self.ensure_one()
        connection = None
        created = self.env["ddfsc.biometric.punch"]
        duplicates = 0
        timezone = pytz.timezone(self.timezone)
        sync_log = self.env["ddfsc.biometric.sync.log"].sudo().create(
            {"device_id": self.id, "trigger": trigger}
        )
        try:
            connection = self._get_zk_connection()
            connection.disable_device()
            events = connection.get_attendance() or []
            for event in events:
                local_time = event.timestamp
                if local_time.tzinfo is None:
                    local_time = timezone.localize(local_time)
                event_time = local_time.astimezone(pytz.utc).replace(tzinfo=None)
                device_code = str(getattr(event, "punch", ""))
                punch_type = "unknown"
                if self.use_device_punch_type:
                    punch_type = {"0": "in", "1": "out"}.get(device_code, "unknown")
                event_key = self.env["ddfsc.biometric.punch"]._make_event_key(
                    self, event.user_id, event_time, punch_type
                )
                if self.env["ddfsc.biometric.punch"].search_count([("event_key", "=", event_key)]):
                    duplicates += 1
                    continue
                created |= self.env["ddfsc.biometric.punch"].create(
                    {
                        "device_id": self.id,
                        "device_user_id": str(event.user_id),
                        "event_time": event_time,
                        "punch_type": punch_type,
                        "event_key": event_key,
                        "raw_payload": json.dumps(
                            {
                                "uid": getattr(event, "uid", None),
                                "user_id": event.user_id,
                                "timestamp": event.timestamp.isoformat(),
                                "status": getattr(event, "status", None),
                                "punch": getattr(event, "punch", None),
                            }
                        ),
                    }
                )
            now = fields.Datetime.now()
            self.write(
                {
                    "last_sync_at": now,
                    "last_sync_status": "success",
                    "last_sync_error": False,
                    "next_sync_at": now + timedelta(minutes=max(self.sync_interval_minutes, 5)),
                }
            )
            sync_log.write(
                {
                    "finished_at": now,
                    "status": "success",
                    "imported_count": len(created),
                    "duplicate_count": duplicates,
                }
            )
        except Exception as error:
            _logger.exception("ZKTeco download failed for %s", self.display_name)
            now = fields.Datetime.now()
            message = str(error)
            self.write(
                {
                    "last_sync_status": "failed",
                    "last_sync_error": message,
                    "next_sync_at": now + timedelta(minutes=max(self.sync_interval_minutes, 5)),
                }
            )
            sync_log.write({"finished_at": now, "status": "failed", "error_message": message})
            if trigger == "manual":
                raise UserError(_("Punch download failed for %(device)s: %(error)s", device=self.display_name, error=error)) from error
        finally:
            if connection:
                try:
                    connection.enable_device()
                finally:
                    connection.disconnect()
        return created, duplicates

    def _cron_download_punches(self):
        now = fields.Datetime.now()
        devices = self.search(
            [
                ("active", "=", True),
                ("device_type", "=", "zk"),
                ("auto_sync", "=", True),
                "|",
                ("next_sync_at", "=", False),
                ("next_sync_at", "<=", now),
            ]
        )
        for device in devices:
            device._download_punches(trigger="scheduled")
