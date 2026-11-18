"""Weighing tickets received from the indicator (IDé 500 printer output).

The operator weighs on the indicator as usual (F1 entry, F2 exit). Its COM1
is set to a printer driver, so each printed ticket also reaches the scale
bridge, which sends it here. A weighbridge ticket in Odoo is then completed
from it: gross, tare, net and the legal DSD number come from the indicator,
not from typing.
"""

import re
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


def plate_key(value):
    """Compare plates without spaces, dashes or case: '3-98673 AA' == '398673aa'."""
    return re.sub(r"[^0-9A-Z]", "", (value or "").upper())


class DdfscWeighbridgeIndicatorTicket(models.Model):
    _name = "ddfsc.weighbridge.indicator.ticket"
    _description = "Indicator Weighing Ticket"
    _order = "weighing_date desc, id desc"
    _rec_name = "display_label"

    scale_id = fields.Many2one("ddfsc.weighbridge.scale", required=True, ondelete="restrict", index=True)
    weighing_no = fields.Char(string="Weighing No.", index=True)
    weighing_type = fields.Char(help="IO / ES: entry-exit weighing, TF: tare file, TM / MT: gross-tare-net.")
    dsd_no = fields.Char(string="DSD No.", index=True)
    vehicle = fields.Char(string="Vehicle No.", index=True)
    vehicle_key = fields.Char(compute="_compute_vehicle_key", store=True, index=True)
    first_date = fields.Datetime(string="First Weighing")
    weighing_date = fields.Datetime(string="Weighing Date")
    gross = fields.Float(string="Gross (kg)", digits=(16, 3))
    tare = fields.Float(string="Tare (kg)", digits=(16, 3))
    net = fields.Float(string="Net (kg)", digits=(16, 3))
    raw = fields.Text(string="Printed Ticket", readonly=True)
    received_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    ticket_id = fields.Many2one("ddfsc.weighbridge.ticket", string="Used on Ticket", readonly=True, copy=False)
    display_label = fields.Char(compute="_compute_display_label")

    _unique_weighing = models.Constraint(
        "unique(scale_id, weighing_no, dsd_no)", "This indicator ticket was already received.")

    @api.depends("vehicle")
    def _compute_vehicle_key(self):
        for record in self:
            record.vehicle_key = plate_key(record.vehicle)

    @api.depends("weighing_no", "dsd_no", "vehicle", "net")
    def _compute_display_label(self):
        for record in self:
            record.display_label = _("No %(no)s · DSD %(dsd)s · %(vehicle)s · net %(net)s kg",
                                     no=record.weighing_no or "-", dsd=record.dsd_no or "-",
                                     vehicle=record.vehicle or "-", net=record.net or 0)


class DdfscWeighbridgeScale(models.Model):
    _inherit = "ddfsc.weighbridge.scale"

    @api.model
    def push_indicator_ticket(self, code, values):
        """Called by the scale bridge for every printed ticket of the indicator."""
        if not self.env.user.has_group("ddfsc_weighbridge.group_ddfsc_weighbridge_device") \
                and not self.env.user.has_group("ddfsc_weighbridge.group_ddfsc_weighbridge_manager"):
            raise AccessError(_("Only the weighbridge device account may send indicator tickets."))
        scale = self.sudo().search([("code", "=", code), ("active", "=", True)], limit=1)
        if not scale:
            raise UserError(_("Unknown scale code %s.") % code)
        Ticket = self.env["ddfsc.weighbridge.indicator.ticket"].sudo()
        existing = Ticket.search([
            ("scale_id", "=", scale.id), ("weighing_no", "=", values.get("weighing_no") or False),
            ("dsd_no", "=", values.get("dsd_no") or False),
        ], limit=1)
        if existing:
            return existing.id  # the bridge may resend after a network error
        timezone = pytz.timezone(self.env.company.partner_id.tz or "Africa/Addis_Ababa")

        def utc(value):
            if not value:
                return False
            local = timezone.localize(fields.Datetime.to_datetime(value))
            return local.astimezone(pytz.utc).replace(tzinfo=None)

        gross = float(values.get("gross") or values.get("first_weight") or 0.0)
        tare = float(values.get("tare") or 0.0)
        record = Ticket.create({
            "scale_id": scale.id,
            "weighing_no": values.get("weighing_no") or False,
            "weighing_type": values.get("weighing_type") or False,
            "dsd_no": values.get("dsd_no") or False,
            "vehicle": (values.get("vehicle") or "").strip() or False,
            "first_date": utc(values.get("first_date")),
            "weighing_date": utc(values.get("weighing_date")) or fields.Datetime.now(),
            "gross": gross,
            "tare": tare,
            "net": float(values.get("net") or max(gross - tare, 0.0)),
            "raw": values.get("raw") or False,
        })
        scale.write({"last_dsd": record.dsd_no, "last_read_at": fields.Datetime.now(),
                     "last_raw": (record.raw or "")[-120:]})
        return record.id


class DdfscWeighbridgeTicket(models.Model):
    _inherit = "ddfsc.weighbridge.ticket"

    indicator_ticket_id = fields.Many2one(
        "ddfsc.weighbridge.indicator.ticket", string="Indicator Ticket", copy=False,
        domain="[('ticket_id', '=', False), ('scale_id', '=', scale_id)]",
        help="The ticket printed by the weighbridge indicator for this vehicle.")

    def _ddfsc_find_indicator_ticket(self):
        self.ensure_one()
        since = fields.Datetime.now() - timedelta(days=2)
        candidates = self.env["ddfsc.weighbridge.indicator.ticket"].search([
            ("ticket_id", "=", False), ("scale_id", "=", self.scale_id.id),
            ("vehicle_key", "=", plate_key(self.vehicle_plate)), ("received_at", ">=", since),
            ("tare", ">", 0),
        ], order="weighing_date desc, id desc")
        return candidates[:1]

    def action_fill_from_indicator(self):
        """Complete this ticket from the indicator's printed ticket (same truck)."""
        for ticket in self:
            if ticket.state not in ("draft", "first_recorded"):
                raise UserError(_("Only an open ticket can be filled from the indicator."))
            if not ticket.scale_id:
                raise UserError(_("Choose the scale first."))
            source = ticket.indicator_ticket_id or ticket._ddfsc_find_indicator_ticket()
            if not source:
                raise UserError(_(
                    "No indicator ticket with gross and tare for vehicle %s has arrived in the last two days. "
                    "Finish the weighing on the indicator (exit weighing) and try again, or pick the "
                    "indicator ticket by hand.") % (ticket.vehicle_plate or "-"))
            if source.ticket_id and source.ticket_id != ticket:
                raise UserError(_("Indicator ticket %s is already used on %s.") % (
                    source.display_label, source.ticket_id.name))
            if source.gross <= 0 or source.tare <= 0 or source.tare >= source.gross:
                raise UserError(_("Indicator ticket %s has no valid gross and tare.") % source.display_label)
            context = {"ddfsc_weight_source": "scale", "ddfsc_weight_dsd": source.dsd_no}
            first_field, second_field = ticket._first_field(), ticket._second_field()
            first_value = source.gross if first_field == "gross_weight" else source.tare
            second_value = source.tare if first_field == "gross_weight" else source.gross
            if ticket.state == "draft":
                ticket.write({first_field: first_value})
                ticket.with_context(**context).action_record_first_weight()
            ticket.write({second_field: second_value})
            ticket.with_context(**context).action_record_second_weight()
            ticket.write({"indicator_ticket_id": source.id, "reference": ticket.reference or source.weighing_no})
            source.sudo().ticket_id = ticket
            ticket.message_post(body=_("Weights taken from indicator ticket %s.") % source.display_label)
        return True
