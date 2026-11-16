"""Live connection to the weighbridge indicator (Master-K IDé 500).

The indicator stays the legal weighing instrument. A small bridge program on
the weighbridge PC (``tools/scale_bridge.py``) reads its serial / USB output
and pushes every reading here through ``push_reading``. The ticket then takes
the weight from the scale instead of a typed number, together with the
indicator's DSD (alibi memory) number, so the printed slip and Odoo match.
"""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class DdfscWeighbridgeScale(models.Model):
    _name = "ddfsc.weighbridge.scale"
    _description = "Weighbridge Scale"

    name = fields.Char(required=True, default="Weighbridge")
    code = fields.Char(required=True, default="WB1", help="Identifier the bridge program sends with each reading.")
    model = fields.Char(default="Master-K IDé 500")
    active = fields.Boolean(default=True)
    max_age_seconds = fields.Integer(
        string="Reading Valid For (s)", default=10,
        help="A captured weight must be at most this old; older readings mean the bridge is not running.")
    min_weight = fields.Float(string="Minimum Weight (kg)", default=20.0,
                              help="Readings below this are treated as an empty platform.")
    last_weight = fields.Float(string="Last Weight (kg)", readonly=True, digits=(16, 3))
    last_stable = fields.Boolean(string="Stable", readonly=True)
    last_read_at = fields.Datetime(string="Last Reading", readonly=True)
    last_raw = fields.Char(string="Last Raw Frame", readonly=True)
    last_dsd = fields.Char(string="Last DSD No.", readonly=True)
    is_online = fields.Boolean(string="Online", compute="_compute_is_online")

    _code_unique = models.Constraint("unique(code)", "Each scale needs its own code.")

    def _compute_is_online(self):
        now = fields.Datetime.now()
        for scale in self:
            scale.is_online = bool(scale.last_read_at) and \
                now - scale.last_read_at <= timedelta(seconds=max(scale.max_age_seconds, 1))

    @api.model
    def push_reading(self, code, weight, stable=True, raw=None, dsd=None):
        """Called by the bridge program (JSON-RPC / XML-RPC) for every reading."""
        if not self.env.user.has_group("ddfsc_weighbridge.group_ddfsc_weighbridge_device") \
                and not self.env.user.has_group("ddfsc_weighbridge.group_ddfsc_weighbridge_manager"):
            raise AccessError(_("Only the weighbridge device account may send scale readings."))
        scale = self.sudo().search([("code", "=", code), ("active", "=", True)], limit=1)
        if not scale:
            raise UserError(_("Unknown scale code %s.") % code)
        values = {
            "last_weight": float(weight),
            "last_stable": bool(stable),
            "last_read_at": fields.Datetime.now(),
            "last_raw": (raw or "")[:120],
        }
        if dsd:
            values["last_dsd"] = str(dsd)[:32]
        scale.write(values)
        return True

    def _current_weight(self):
        """The weight a ticket may capture now, or a clear reason why not."""
        self.ensure_one()
        if not self.is_online:
            raise UserError(_(
                "No recent reading from %(scale)s (last: %(last)s). Check that the scale bridge is running "
                "on the weighbridge PC, or enter the weight manually.",
                scale=self.name, last=self.last_read_at or _("never")))
        if not self.last_stable:
            raise UserError(_("The weight is not stable yet. Wait for the indicator to settle and try again."))
        if self.last_weight < self.min_weight:
            raise UserError(_("The platform reads %(weight)s kg: no vehicle on the scale.", weight=self.last_weight))
        return self.last_weight, self.last_dsd


class DdfscWeighbridgeTicket(models.Model):
    _inherit = "ddfsc.weighbridge.ticket"

    # No field default: existing tickets get the column while the scale table
    # may not exist yet during the upgrade. New tickets get the scale in create().
    scale_id = fields.Many2one("ddfsc.weighbridge.scale", string="Scale")
    scale_online = fields.Boolean(related="scale_id.is_online", string="Scale Online")
    first_weight_source = fields.Selection([("scale", "From Scale"), ("manual", "Typed")], readonly=True, copy=False)
    second_weight_source = fields.Selection([("scale", "From Scale"), ("manual", "Typed")], readonly=True, copy=False)
    first_dsd = fields.Char(string="First Weighing DSD No.", readonly=True, copy=False)
    second_dsd = fields.Char(string="Second Weighing DSD No.", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        scale = self.env["ddfsc.weighbridge.scale"].search([], limit=1)
        for values in vals_list:
            if scale and not values.get("scale_id"):
                values["scale_id"] = scale.id
        return super().create(vals_list)

    def _first_field(self):
        return "gross_weight" if self.first_weight_kind == "gross" else "tare_weight"

    def _second_field(self):
        return "tare_weight" if self.first_weight_kind == "gross" else "gross_weight"

    def action_capture_first_weight(self):
        for ticket in self:
            if ticket.state != "draft":
                raise UserError(_("The first weight has already been recorded for this ticket."))
            if not ticket.scale_id:
                raise UserError(_("Choose the scale first."))
            weight, dsd = ticket.scale_id._current_weight()
            ticket.write({ticket._first_field(): weight})
            ticket.with_context(ddfsc_weight_source="scale", ddfsc_weight_dsd=dsd).action_record_first_weight()
        return True

    def action_capture_second_weight(self):
        for ticket in self:
            if ticket.state != "first_recorded":
                raise UserError(_("Record the first weight before recording the second."))
            if not ticket.scale_id:
                raise UserError(_("Choose the scale first."))
            weight, dsd = ticket.scale_id._current_weight()
            ticket.write({ticket._second_field(): weight})
            ticket.with_context(ddfsc_weight_source="scale", ddfsc_weight_dsd=dsd).action_record_second_weight()
        return True

    def action_record_first_weight(self):
        result = super().action_record_first_weight()
        source = self.env.context.get("ddfsc_weight_source", "manual")
        self.write({"first_weight_source": source, "first_dsd": self.env.context.get("ddfsc_weight_dsd") or False})
        if source == "manual":
            for ticket in self:
                ticket.message_post(body=_("First weight typed manually: %(weight)s kg.",
                                           weight=ticket[ticket._first_field()]))
        return result

    def action_record_second_weight(self):
        result = super().action_record_second_weight()
        source = self.env.context.get("ddfsc_weight_source", "manual")
        self.write({"second_weight_source": source, "second_dsd": self.env.context.get("ddfsc_weight_dsd") or False})
        if source == "manual":
            for ticket in self:
                ticket.message_post(body=_("Second weight typed manually: %(weight)s kg.",
                                           weight=ticket[ticket._second_field()]))
        return result

    def action_complete(self):
        # Both weights read from the indicator (with their DSD numbers) are the
        # record; a photo of the printed slip is only needed for typed weights.
        captured = self.filtered(lambda ticket: ticket.first_weight_source == "scale"
                                 and ticket.second_weight_source == "scale")
        for ticket in captured:
            if ticket.state != "weighed":
                raise UserError(_("Record both gross and tare weights before completing the ticket."))
            if ticket.net_weight <= 0:
                raise UserError(_("Net weight must be greater than zero."))
            ticket.write({"state": "completed", "completed_by_id": self.env.user.id})
            ticket.message_post(body=_(
                "Weighbridge ticket completed from the scale. Gross: %(gross).3f kg; Tare: %(tare).3f kg; "
                "Net: %(net).3f kg. DSD %(first)s / %(second)s.",
                gross=ticket.gross_weight, tare=ticket.tare_weight, net=ticket.net_weight,
                first=ticket.first_dsd or "-", second=ticket.second_dsd or "-"))
        return super(DdfscWeighbridgeTicket, self - captured).action_complete() if self - captured else True
