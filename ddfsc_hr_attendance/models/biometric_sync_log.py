from odoo import fields, models
from odoo.exceptions import UserError


class DdfscBiometricSyncLog(models.Model):
    _name = "ddfsc.biometric.sync.log"
    _description = "Biometric Synchronization Log"
    _order = "started_at desc, id desc"

    device_id = fields.Many2one(
        "ddfsc.biometric.device", required=True, ondelete="restrict", index=True
    )
    company_id = fields.Many2one(related="device_id.company_id", store=True, index=True)
    started_at = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
    finished_at = fields.Datetime(readonly=True)
    trigger = fields.Selection(
        [("manual", "Manual"), ("scheduled", "Scheduled")], required=True, readonly=True
    )
    status = fields.Selection(
        [("running", "Running"), ("success", "Success"), ("failed", "Failed")],
        required=True,
        default="running",
        readonly=True,
        index=True,
    )
    imported_count = fields.Integer(readonly=True)
    duplicate_count = fields.Integer(readonly=True)
    error_message = fields.Text(readonly=True)

    def unlink(self):
        if not self.env.context.get("module_uninstall"):
            raise UserError("Synchronization history is an audit record and cannot be deleted.")
        return super().unlink()
