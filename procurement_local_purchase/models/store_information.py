"""Store information on purchase requisition lines.

The paper Purchase Requisition carries a "Store Information" block for every
item: stock on hand, minimum stock and annual consumption, so the approver
sees why the quantity is asked for.
"""

from datetime import timedelta

from odoo import api, fields, models


class LocalPurchaseRequisitionLine(models.Model):
    _inherit = 'local.purchase.requisition.line'

    store_qty_on_hand = fields.Float(
        string='Stock on Hand', compute='_compute_store_information', digits='Product Unit')
    store_min_qty = fields.Float(
        string='Min. Stock', compute='_compute_store_information', digits='Product Unit',
        help='Minimum quantity of the replenishment rule, when one exists.')
    store_annual_consumption = fields.Float(
        string='Annual Consumption', compute='_compute_store_information', digits='Product Unit',
        help='Quantity that left the stores for production, customers or use in the last 365 days.')

    @api.depends('product_id')
    def _compute_store_information(self):
        since = fields.Datetime.now() - timedelta(days=365)
        for line in self:
            product = line.product_id
            if not product:
                line.store_qty_on_hand = line.store_min_qty = line.store_annual_consumption = 0.0
                continue
            # Store figures are shown to requesters who may not hold stock rights.
            product = product.sudo()
            line.store_qty_on_hand = product.qty_available
            orderpoint = self.env['stock.warehouse.orderpoint'].sudo().search(
                [('product_id', '=', product.id)], limit=1)
            line.store_min_qty = orderpoint.product_min_qty if orderpoint else 0.0
            moves = self.env['stock.move'].sudo().search([
                ('product_id', '=', product.id), ('state', '=', 'done'), ('date', '>=', since),
                ('location_id.usage', '=', 'internal'), ('location_dest_id.usage', '!=', 'internal'),
                ('location_dest_id.usage', '!=', 'supplier'),
            ])
            line.store_annual_consumption = sum(moves.mapped('product_qty'))
