from odoo import api, fields, models


class QcInspection(models.Model):
    _inherit = "qc.inspection"

    ddfsc_lot_id = fields.Many2one(
        "stock.lot",
        string="DDFSC Lot / Batch",
        index=True,
        ondelete="cascade",
        help="Factory lot governed by this inspection.",
    )
    ddfsc_checkpoint = fields.Selection(
        related="ddfsc_lot_id.quality_checkpoint",
        string="Factory Checkpoint",
        store=True,
        index=True,
    )

    @api.onchange("ddfsc_lot_id")
    def _onchange_ddfsc_lot_id(self):
        for inspection in self:
            if inspection.ddfsc_lot_id:
                inspection.object_id = inspection.ddfsc_lot_id.product_id

    def action_open_ddfsc_lot(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.ddfsc_lot_id.display_name,
            "res_model": "stock.lot",
            "view_mode": "form",
            "res_id": self.ddfsc_lot_id.id,
        }
