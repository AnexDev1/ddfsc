from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    # Kept for historical plant types that may still exist archived in the DB.
    ddfsc_document_type = fields.Selection(
        [
            ('wheat_receiving', 'Wheat Receiving'),
            ('store_receipt', 'Store Receipt'),
            ('wheat_to_silo', 'Wheat to Silo'),
            ('silo_issue', 'Silo Issue'),
            ('flour_transfer', 'Flour Transfer'),
            ('store_requisition', 'Store Request'),
            ('byproduct_return', 'By-product to Store'),
            ('fg_receiving', 'Finished Goods Receiving'),
        ],
        string='Plant Form',
    )


class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'ddfsc.approval.mixin']

    ddfsc_production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        index=True,
        copy=False,
    )
    ddfsc_store_request_id = fields.Many2one(
        'ddfsc.store.request',
        string='Store Transfer Request',
        copy=False,
        index=True,
    )
    ddfsc_document_type = fields.Selection(
        related='picking_type_id.ddfsc_document_type',
        store=True,
    )

    def _ddfsc_approval_role(self):
        self.ensure_one()
        return ''

    @api.depends('ddfsc_document_type', 'ddfsc_store_request_id')
    def _compute_ddfsc_needs_approval(self):
        super()._compute_ddfsc_needs_approval()

    def button_validate(self):
        self._ddfsc_ensure_approved()
        for picking in self:
            if picking.picking_type_code == 'incoming':
                continue
            if picking.location_dest_id.usage == 'inventory':
                continue
            for line in picking.move_line_ids:
                lot = line.lot_id
                if not lot:
                    continue
                source_use = picking.location_id.ddfsc_silo_use
                if source_use and (not lot.ddfsc_gm_approved or lot.ddfsc_wheat_use != source_use):
                    raise UserError(_(
                        'Lot %s can leave this silo only when the general manager has approved it for %s.',
                        lot.name,
                        dict(picking.location_id._fields['ddfsc_silo_use'].selection).get(source_use),
                    ))
                dest_use = picking.location_dest_id.ddfsc_silo_use
                if dest_use and (not lot.ddfsc_gm_approved or lot.ddfsc_wheat_use != dest_use):
                    raise UserError(_(
                        'Lot %s cannot enter the %s silo until the general manager has approved it for that use.',
                        lot.name,
                        dict(picking.location_dest_id._fields['ddfsc_silo_use'].selection).get(dest_use),
                    ))
                if line.product_id.ddfsc_is_flour and picking.location_id.ddfsc_flour_hold:
                    if lot.ddfsc_quality_state not in ('pass', 'released'):
                        raise UserError(_(
                            'Flour lot %s has to pass quality before it leaves %s.',
                            lot.name,
                            picking.location_id.display_name,
                        ))
            held = picking.move_line_ids.filtered(
                lambda line: line.lot_id and line.lot_id.ddfsc_quality_state == 'hold'
            )
            if held:
                names = ', '.join(sorted(set(held.lot_id.mapped('name'))))
                raise UserError(_(
                    'These lots are on quality hold and cannot leave the current location: %s. '
                    'Release them from the lot form, or scrap them.'
                ) % names)
        res = super().button_validate()
        self.filtered(lambda picking: picking.state == 'done').mapped(
            'ddfsc_store_request_id'
        )._ddfsc_mark_received()
        return res
