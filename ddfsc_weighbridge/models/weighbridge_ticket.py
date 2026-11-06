from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DdfscWeighbridgeTicket(models.Model):
    _name = "ddfsc.weighbridge.ticket"
    _description = "Weighbridge Ticket"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "weigh_out_at desc, first_weight_at desc, create_date desc"
    _check_company_auto = True

    name = fields.Char(
        string="Ticket Number", readonly=True, copy=False, default=lambda self: _("New"),
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("first_recorded", "First Weight Recorded"),
            ("weighed", "Weights Complete"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft", required=True, readonly=True, tracking=True,
    )
    operation_type = fields.Selection(
        [
            ("incoming", "Incoming Receipt"),
            ("outgoing", "Outgoing Delivery"),
            ("internal", "Internal Transfer"),
        ],
        string="Operation", default="incoming", required=True, tracking=True,
        help="Choose why the vehicle is being weighed. This does not validate the linked stock document.",
    )
    first_weight_kind = fields.Selection(
        [("gross", "Gross Weight First"), ("tare", "Tare Weight First")],
        string="First Weighing", default="gross", required=True, tracking=True,
        help="Incoming loaded vehicles normally record gross first. Empty outgoing vehicles normally record tare first.",
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True,
    )
    partner_id = fields.Many2one(
        "res.partner", string="Supplier / Customer", tracking=True,
        check_company=True,
    )
    vehicle_plate = fields.Char(required=True, tracking=True)
    driver_name = fields.Char(tracking=True)
    product_id = fields.Many2one(
        "product.product", required=True, tracking=True, check_company=True,
        domain="[('type', '!=', 'service')]",
    )
    purchase_id = fields.Many2one(
        "purchase.order", string="Purchase Order", tracking=True, check_company=True,
        domain="[('state', 'in', ('purchase', 'done'))]",
    )
    picking_id = fields.Many2one(
        "stock.picking", string="Stock Document", tracking=True, check_company=True,
        domain="[('state', '!=', 'cancel')]",
        help="Receipt, delivery, or internal transfer supported by this weighing ticket. Inventory is not validated from this ticket.",
    )
    reference = fields.Char(string="External / Paper Slip Reference", tracking=True)

    gross_weight = fields.Float(string="Gross Weight (kg)", digits=(16, 3), tracking=True)
    tare_weight = fields.Float(string="Tare Weight (kg)", digits=(16, 3), tracking=True)
    net_weight = fields.Float(string="Net Weight (kg)", compute="_compute_net_weight", store=True, digits=(16, 3), tracking=True)
    first_weight_at = fields.Datetime(readonly=True, copy=False, tracking=True)
    first_weight_by_id = fields.Many2one("res.users", readonly=True, copy=False, string="First Weight Recorded By")
    second_weight_at = fields.Datetime(readonly=True, copy=False, tracking=True)
    second_weight_by_id = fields.Many2one("res.users", readonly=True, copy=False, string="Second Weight Recorded By")
    weigh_out_at = fields.Datetime(readonly=True, copy=False, tracking=True)
    completed_by_id = fields.Many2one("res.users", readonly=True, copy=False, string="Completed By")
    cancellation_reason = fields.Text(copy=False, tracking=True)
    notes = fields.Text()

    attachment_count = fields.Integer(compute="_compute_attachment_count", string="Slip Attachments")
    document_reference = fields.Char(compute="_compute_document_reference", string="Linked Document", store=False)

    @api.depends("gross_weight", "tare_weight")
    def _compute_net_weight(self):
        for ticket in self:
            ticket.net_weight = max(ticket.gross_weight - ticket.tare_weight, 0.0)

    @api.depends("picking_id", "purchase_id")
    def _compute_document_reference(self):
        for ticket in self:
            ticket.document_reference = ticket.picking_id.display_name or ticket.purchase_id.display_name

    def _compute_attachment_count(self):
        attachments = self.env["ir.attachment"].read_group(
            [("res_model", "=", self._name), ("res_id", "in", self.ids)], ["res_id"], ["res_id"]
        ) if self.ids else []
        counts = {item["res_id"]: item["res_id_count"] for item in attachments}
        for ticket in self:
            ticket.attachment_count = counts.get(ticket.id, 0)

    @api.onchange("purchase_id")
    def _onchange_purchase_id(self):
        for ticket in self:
            if ticket.purchase_id:
                ticket.partner_id = ticket.purchase_id.partner_id
                receipts = ticket.purchase_id.picking_ids.filtered(
                    lambda picking: picking.picking_type_code == "incoming" and picking.state != "cancel"
                )
                if len(receipts) == 1:
                    ticket.picking_id = receipts

    @api.onchange("operation_type")
    def _onchange_operation_type(self):
        for ticket in self:
            ticket.first_weight_kind = "tare" if ticket.operation_type == "outgoing" else "gross"

    @api.onchange("picking_id")
    def _onchange_picking_id(self):
        for ticket in self:
            if ticket.picking_id:
                ticket.partner_id = ticket.picking_id.partner_id
                if ticket.picking_id.purchase_id:
                    ticket.purchase_id = ticket.picking_id.purchase_id

    @api.constrains("gross_weight", "tare_weight")
    def _check_weight_order(self):
        for ticket in self:
            if ticket.gross_weight < 0 or ticket.tare_weight < 0:
                raise ValidationError(_("Weights cannot be negative."))
            if ticket.tare_weight and ticket.gross_weight and ticket.tare_weight >= ticket.gross_weight:
                raise ValidationError(_("Tare weight must be less than gross weight."))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("name", _("New")) == _("New"):
                values["name"] = self.env["ir.sequence"].next_by_code("ddfsc.weighbridge.ticket") or _("New")
        return super().create(vals_list)

    def write(self, values):
        """Keep captured measurements auditable even when a client bypasses the form view."""
        for ticket in self:
            if ticket.state in ("completed", "cancelled"):
                blocked = set(values) - {"message_follower_ids", "message_ids", "activity_ids"}
                if blocked:
                    raise UserError(_("A completed or cancelled ticket cannot be changed."))
            first_field = "gross_weight" if ticket.first_weight_kind == "gross" else "tare_weight"
            second_field = "tare_weight" if ticket.first_weight_kind == "gross" else "gross_weight"
            if ticket.state != "draft" and first_field in values:
                raise UserError(_("The first captured weight is locked."))
            if ticket.state not in ("draft", "first_recorded") and second_field in values:
                raise UserError(_("The second captured weight is locked."))
        return super().write(values)

    def _require_open_ticket(self):
        if self.state in ("completed", "cancelled"):
            raise UserError(_("A completed or cancelled ticket cannot be changed."))

    def _check_context_before_weighing(self):
        for ticket in self:
            if not ticket.vehicle_plate:
                raise UserError(_("Enter the vehicle plate before recording a weight."))
            if not ticket.product_id:
                raise UserError(_("Choose the weighed product before recording a weight."))
            if ticket.operation_type == "incoming" and not (ticket.purchase_id or ticket.picking_id):
                raise UserError(_("Link an incoming ticket to its Purchase Order or Receipt before recording a weight."))
            if ticket.operation_type in ("outgoing", "internal") and not ticket.picking_id:
                raise UserError(_("Link this ticket to its Delivery or Internal Transfer before recording a weight."))
            expected_picking_code = {
                "incoming": "incoming",
                "outgoing": "outgoing",
                "internal": "internal",
            }[ticket.operation_type]
            if ticket.picking_id and ticket.picking_id.picking_type_code != expected_picking_code:
                raise UserError(_(
                    "The linked stock document must be a %(operation)s operation for this ticket.",
                    operation=dict(ticket._fields["operation_type"].selection)[ticket.operation_type],
                ))
            if ticket.purchase_id and ticket.picking_id.purchase_id and ticket.picking_id.purchase_id != ticket.purchase_id:
                raise UserError(_("The selected receipt belongs to a different Purchase Order."))

    def action_record_first_weight(self):
        for ticket in self:
            ticket._require_open_ticket()
            ticket._check_context_before_weighing()
            if ticket.state != "draft":
                raise UserError(_("The first weight has already been recorded for this ticket."))
            first_weight = ticket.gross_weight if ticket.first_weight_kind == "gross" else ticket.tare_weight
            if first_weight <= 0:
                label = _("gross") if ticket.first_weight_kind == "gross" else _("tare")
                raise UserError(_("Enter the first %(label)s weight in kilograms before recording it.", label=label))
            ticket.write({
                "state": "first_recorded",
                "first_weight_at": fields.Datetime.now(),
                "first_weight_by_id": self.env.user.id,
            })
        return True

    def action_record_second_weight(self):
        for ticket in self:
            ticket._require_open_ticket()
            if ticket.state != "first_recorded":
                raise UserError(_("Record the first weight before recording the second."))
            second_weight = ticket.tare_weight if ticket.first_weight_kind == "gross" else ticket.gross_weight
            if second_weight <= 0:
                label = _("tare") if ticket.first_weight_kind == "gross" else _("gross")
                raise UserError(_("Enter the second %(label)s weight in kilograms before recording it.", label=label))
            if ticket.tare_weight >= ticket.gross_weight:
                raise UserError(_("Tare weight must be less than gross weight."))
            ticket.write({
                "state": "weighed",
                "second_weight_at": fields.Datetime.now(),
                "second_weight_by_id": self.env.user.id,
                "weigh_out_at": fields.Datetime.now(),
            })
        return True

    def action_complete(self):
        attachment_model = self.env["ir.attachment"]
        for ticket in self:
            ticket._require_open_ticket()
            if ticket.state != "weighed":
                raise UserError(_("Record both gross and tare weights before completing the ticket."))
            if ticket.net_weight <= 0:
                raise UserError(_("Net weight must be greater than zero."))
            if not attachment_model.search_count([("res_model", "=", self._name), ("res_id", "=", ticket.id)]):
                raise UserError(_("Attach a scan or photo of the printed weighbridge slip before completing the ticket."))
            ticket.write({"state": "completed", "completed_by_id": self.env.user.id})
            ticket.message_post(body=_(
                "Weighbridge ticket completed. Gross: %(gross).3f kg; Tare: %(tare).3f kg; Net: %(net).3f kg.",
                gross=ticket.gross_weight, tare=ticket.tare_weight, net=ticket.net_weight,
            ))
        return True

    def action_cancel(self):
        for ticket in self:
            ticket._require_open_ticket()
            if not ticket.cancellation_reason:
                raise UserError(_("Enter a cancellation reason before cancelling the ticket."))
            ticket.write({"state": "cancelled"})
        return True

    def action_open_attachments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Printed Scale Slips"),
            "res_model": "ir.attachment",
            "view_mode": "list,form",
            "domain": [("res_model", "=", self._name), ("res_id", "=", self.id)],
            "context": {"default_res_model": self._name, "default_res_id": self.id},
        }

    def action_open_picking(self):
        self.ensure_one()
        if not self.picking_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": self.picking_id.display_name,
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.picking_id.id,
        }
