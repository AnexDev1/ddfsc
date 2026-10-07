from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
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
