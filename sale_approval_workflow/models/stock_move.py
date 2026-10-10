from odoo import models, fields

class StockMove(models.Model):
    _inherit = 'stock.move'

    requested_lot_id = fields.Many2one(
        'stock.lot', 
        string='Requested Lot', 
        related='sale_line_id.lot_id', 
        store=True
    )

    def _update_reserved_quantity_vals(self, need, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        # If this move comes from a sale order line that specifically requested a lot, force reservation for that lot
        if not lot_id and self.sale_line_id and self.sale_line_id.lot_id:
            lot_id = self.sale_line_id.lot_id
            
        return super()._update_reserved_quantity_vals(
            need, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict
        )
