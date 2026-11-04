import base64
import csv
import io
import json
from datetime import datetime

import pytz

from odoo import _, fields, models
from odoo.exceptions import UserError


class DdfscAttendanceImportWizard(models.TransientModel):
    _name = "ddfsc.attendance.import.wizard"
    _description = "Import Biometric Attendance Punches"

    device_id = fields.Many2one("ddfsc.biometric.device", required=True)
    file = fields.Binary(required=True)
    filename = fields.Char()
    process_after_import = fields.Boolean(default=False)

    def action_import(self):
        self.ensure_one()
        try:
            content = base64.b64decode(self.file).decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(content)))
        except Exception as error:
            raise UserError(_("The file must be a valid UTF-8 CSV: %s", error)) from error
        required = {"device_user_id", "timestamp"}
        if not rows or not required.issubset(rows[0]):
            raise UserError(_("CSV columns must include device_user_id and timestamp."))

        timezone = pytz.timezone(self.device_id.timezone)
        Punch = self.env["ddfsc.biometric.punch"]
        created = Punch
        duplicates = 0
        for line_number, row in enumerate(rows, start=2):
            try:
                local_time = datetime.fromisoformat(row["timestamp"].strip())
                if local_time.tzinfo is None:
                    local_time = timezone.localize(local_time)
                utc_time = local_time.astimezone(pytz.utc).replace(tzinfo=None)
                punch_type = row.get("punch_type", "unknown").strip().lower() or "unknown"
                aliases = {"check in": "in", "check-in": "in", "check out": "out", "check-out": "out"}
                punch_type = aliases.get(punch_type, punch_type)
                if punch_type not in ("in", "out", "unknown"):
                    raise ValueError("punch_type must be in, out, or unknown")
                event_key = Punch._make_event_key(
                    self.device_id, row["device_user_id"], utc_time, punch_type
                )
                if Punch.search_count([("event_key", "=", event_key)]):
                    duplicates += 1
                    continue
                created |= Punch.create(
                    {
                        "device_id": self.device_id.id,
                        "device_user_id": row["device_user_id"],
                        "event_time": utc_time,
                        "punch_type": punch_type,
                        "event_key": event_key,
                        "raw_payload": json.dumps(row, ensure_ascii=False),
                    }
                )
            except Exception as error:
                raise UserError(_("CSV line %(line)s is invalid: %(error)s", line=line_number, error=error)) from error
        self.device_id.last_sync_at = fields.Datetime.now()
        if self.process_after_import:
            created.action_process()
        return {
            "type": "ir.actions.act_window",
            "name": _("Imported Punches (%(created)s new, %(duplicates)s duplicates)", created=len(created), duplicates=duplicates),
            "res_model": "ddfsc.biometric.punch",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
        }
