from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    ddfsc_document_type = fields.Selection(
        [
            ('wheat_purchase', 'Wheat Receiving'),
            ('store_purchase', 'Store Receipt'),
            ('wheat_to_silo', 'Wheat to Silo'),
            ('silo_issue', 'Silo Issue'),
            ('flour_transfer', 'Flour Transfer'),
            ('store_requisition', 'Store Requisition'),
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
        string='Store Requisition',
        copy=False,
        index=True,
    )
    ddfsc_document_type = fields.Selection(
        related='picking_type_id.ddfsc_document_type',
        store=True,
    )
    ddfsc_board_open = fields.Float(string='Board Opening')
    ddfsc_board_close = fields.Float(string='Board Closing')
    ddfsc_impurity_qtl = fields.Float(string='Impurity (qtl)')
    ddfsc_wheat_qtl = fields.Float(string='Wheat (qtl)', compute='_compute_ddfsc_board_wheat')
    ddfsc_cleaned_qtl = fields.Float(string='Cleaned Wheat (qtl)', compute='_compute_ddfsc_board_wheat')

    @api.depends('ddfsc_board_open', 'ddfsc_board_close', 'ddfsc_impurity_qtl')
    def _compute_ddfsc_board_wheat(self):
        for picking in self:
            picking.ddfsc_wheat_qtl = (picking.ddfsc_board_open - picking.ddfsc_board_close) * 2
            picking.ddfsc_cleaned_qtl = picking.ddfsc_wheat_qtl - picking.ddfsc_impurity_qtl

    def _ddfsc_approval_role(self):
        self.ensure_one()
        return {
            'wheat_to_silo': 'gm',
            'silo_issue': 'operation',
            'flour_transfer': 'operation',
            'store_requisition': 'operation',
            'byproduct_return': 'operation',
            'fg_receiving': 'operation',
        }.get(self.ddfsc_document_type, '')

    @api.depends('ddfsc_document_type')
    def _compute_ddfsc_needs_approval(self):
        super()._compute_ddfsc_needs_approval()

    def _ddfsc_check_silo_board(self):
        quintal = self.env.ref('ddfsc_manufacturing.uom_quintal')
        for picking in self:
            if picking.ddfsc_document_type != 'silo_issue':
                continue
            if picking.ddfsc_board_open <= picking.ddfsc_board_close:
                raise UserError(_('The closing board reading has to be lower than the opening reading.'))
            issued = 0.0
            for move in picking.move_ids.filtered(lambda item: item.state != 'cancel'):
                issued += move.product_uom._compute_quantity(move.product_uom_qty, quintal)
            if abs(issued - picking.ddfsc_wheat_qtl) > 0.01:
                raise UserError(_(
                    'The issued quantity is %(issued)s quintals. '
                    'The board difference times 2 is %(wheat)s quintals.',
                    issued=issued,
                    wheat=picking.ddfsc_wheat_qtl,
                ))

    def button_validate(self):
        self._ddfsc_ensure_approved()
        self._ddfsc_check_silo_board()
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
        return super().button_validate()
