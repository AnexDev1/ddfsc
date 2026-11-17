from odoo import _, api, fields, models
from odoo.exceptions import RedirectWarning, UserError


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
            ('qc_release', 'QC Release'),
            ('material_return', 'Material Return to Store'),
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
    ddfsc_quality_lot_ids = fields.Many2many('stock.lot', compute='_compute_ddfsc_quality_lots')
    ddfsc_quality_lot_count = fields.Integer(compute='_compute_ddfsc_quality_lots')

    @api.depends('move_line_ids.lot_id')
    def _compute_ddfsc_quality_lots(self):
        for picking in self:
            lots = picking.move_line_ids.lot_id.filtered('quality_plan_id')
            picking.ddfsc_quality_lot_ids = lots
            picking.ddfsc_quality_lot_count = len(lots)

    def action_view_ddfsc_quality_lots(self):
        self.ensure_one()
        lots = self.ddfsc_quality_lot_ids
        inspection_action = self._ddfsc_quality_inspection_action(lots)
        if inspection_action:
            return inspection_action
        action = self.env['ir.actions.act_window']._for_xml_id('ddfsc_manufacturing.action_ddfsc_qc_lots')
        action['domain'] = [('id', 'in', lots.ids)]
        if len(lots) == 1:
            action.update(view_mode='form', views=[(False, 'form')], res_id=lots.id)
        return action

    def _ddfsc_quality_inspection_action(self, lots):
        if not lots or 'ddfsc.qc.inspection' not in self.env.registry.models:
            return False
        ensure = getattr(lots, '_ensure_qc_inspection', False)
        if ensure:
            ensure()
        inspections = lots.mapped('active_qc_inspection_id').exists()
        if not inspections:
            return False
        if not self.env.ref('ddfsc_quality.action_qc_inspection_document', raise_if_not_found=False):
            return False
        # _for_xml_id reads the action safely for non-admin users (Odoo 19).
        values = self.env['ir.actions.act_window']._for_xml_id('ddfsc_quality.action_qc_inspection_document')
        values['domain'] = [('id', 'in', inspections.ids)]
        if len(inspections) == 1:
            values.update(view_mode='form', views=[(False, 'form')], res_id=inspections.id)
        return values

    def _ddfsc_quality_redirect(self, lots, message):
        action = self.env.ref(
            'ddfsc_quality.action_qc_inspection_document',
            raise_if_not_found=False,
        ) or self.env.ref('ddfsc_manufacturing.action_ddfsc_qc_lots')
        raise RedirectWarning(
            message, action.id, _('Open QC Lot'),
            {'active_ids': lots.ids, 'ddfsc_qc_lot_ids': lots.ids},
        )

    def _ddfsc_approval_role(self):
        self.ensure_one()
        return ''

    def _ddfsc_assign_incoming_lots(self):
        """Create a traceable batch for each unassigned incoming lot line.

        Receiving staff should not be blocked by Odoo's technical lot prompt.
        A supplier batch can still be entered manually before validation; this
        fallback is used only where no lot was supplied.  Serial-tracked
        products are deliberately excluded because every unit needs its own
        serial number.
        """
        Lot = self.env['stock.lot']
        for picking in self.filtered(lambda record: record.picking_type_code == 'incoming'):
            lines = picking.move_line_ids.filtered(
                lambda line: line.product_id.tracking == 'lot' and not line.lot_id
            ).sorted(lambda line: (line.product_id.id, line.id))
            for position, line in enumerate(lines, start=1):
                # Picking names are unique, so this name is safe to retry if a
                # later validation rule blocks the receipt.
                name = 'REC-%s-%02d' % (picking.name.replace('/', '-'), position)
                lot = Lot.search([
                    ('name', '=', name),
                    ('product_id', '=', line.product_id.id),
                    ('company_id', '=', picking.company_id.id),
                ], limit=1)
                if not lot:
                    lot = Lot.create({
                        'name': name,
                        'product_id': line.product_id.id,
                        'company_id': picking.company_id.id,
                    })
                line.lot_id = lot

    @api.depends('ddfsc_document_type', 'ddfsc_store_request_id')
    def _compute_ddfsc_needs_approval(self):
        super()._compute_ddfsc_needs_approval()

    def button_validate(self):
        self._ddfsc_ensure_approved()
        self._ddfsc_assign_incoming_lots()
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
                        picking._ddfsc_quality_redirect(lot, _(
                            'Flour lot %s has to pass quality before it leaves %s.',
                            lot.name,
                            picking.location_id.display_name,
                        ))
                controlled_sources = [
                    self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
                    for xmlid in ('loc_wheat_dock', 'loc_flour_finished', 'loc_pasta_finished',
                                  'loc_macaroni_finished', 'loc_bread_finished', 'loc_biscuit_finished')
                ]
                qc_required = lot.product_id.ddfsc_qc_required
                if qc_required and picking.location_id in controlled_sources \
                        and lot.ddfsc_quality_state not in ('pass', 'released') and not lot.sudo().quality_plan_id:
                    picking._ddfsc_quality_redirect(lot, _(
                        'Lot %(lot)s cannot leave %(location)s: no approved QC plan covers %(product)s yet, '
                        'so there is nothing for the laboratory to fill in. A Quality Manager must approve '
                        'the QC plan for this product (Quality > DDFSC Standards > Acceptance Plans), or release this lot by exception.',
                        lot=lot.name, location=picking.location_id.display_name,
                        product=lot.product_id.display_name,
                    ))
                if qc_required and picking.location_id in controlled_sources \
                        and lot.ddfsc_quality_state not in ('pass', 'released'):
                    picking._ddfsc_quality_redirect(lot, _(
                        'Lot %(lot)s cannot leave %(location)s while QC status is %(status)s. '
                        'Complete every required check, or record an authorized exception.',
                        lot=lot.name,
                        location=picking.location_id.display_name,
                        status=dict(lot._fields['ddfsc_quality_state'].selection).get(lot.ddfsc_quality_state),
                    ))
            held = picking.move_line_ids.filtered(
                lambda line: line.lot_id and line.lot_id.ddfsc_quality_state in ('hold', 'rejected')
            )
            if held:
                names = ', '.join(sorted(set(held.lot_id.mapped('name'))))
                picking._ddfsc_quality_redirect(held.lot_id, _(
                    'These lots are on quality hold and cannot leave the current location: %s. '
                    'Release them from the lot form, or scrap them.'
                ) % names)
        res = super().button_validate()
        # Status follow-up by the system: store staff validate the transfer but
        # do not edit production requests themselves.
        self.sudo().filtered(lambda picking: picking.state == 'done').mapped(
            'ddfsc_store_request_id'
        )._ddfsc_mark_received()
        return res
