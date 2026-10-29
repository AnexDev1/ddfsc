from odoo import _, api, fields, models
from odoo.exceptions import UserError

class StockLot(models.Model):
    _inherit = 'stock.lot'
    ddfsc_quality_state = fields.Selection([('pending', 'Pending'), ('pass', 'Passed'), ('hold', 'On Hold'), ('released', 'Released by Exception'), ('rejected', 'Rejected')], string='Quality Status', default='pending', tracking=True, copy=False)
    quality_check_ids = fields.One2many('ddfsc.quality.check', 'lot_id', string='Quality Checks')
    quality_plan_id = fields.Many2one('ddfsc.quality.plan', compute='_compute_quality_plan', store=True)
    quality_checkpoint = fields.Selection(related='quality_plan_id.checkpoint', store=True)
    quality_release_note = fields.Char(copy=False)
    quality_decision_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    quality_decision_date = fields.Datetime(readonly=True, copy=False)
    ddfsc_wheat_use = fields.Selection([('pasta', 'Pasta'), ('macaroni', 'Macaroni'), ('bread', 'Bread'), ('biscuit', 'Biscuit')], string='Intended Use', tracking=True)
    ddfsc_gm_approved = fields.Boolean(string='General Manager Approved', copy=False, tracking=True)
    ddfsc_hectoliter = fields.Float(string='Hectoliter Weight', tracking=True)
    ddfsc_wheat_receiving_qty = fields.Float(
        string='Quantity in Wheat Receiving', compute='_compute_ddfsc_wheat_receiving_qty',
        digits='Product Unit of Measure',
    )
    ddfsc_quality_progress = fields.Char(string='Tests Completed', compute='_compute_ddfsc_quality_summary')
    ddfsc_quality_location = fields.Char(string='Current Location', compute='_compute_ddfsc_quality_summary')

    @api.depends('quality_check_ids.is_measured', 'quality_plan_id.line_ids', 'quant_ids.quantity', 'quant_ids.location_id')
    def _compute_ddfsc_quality_summary(self):
        for lot in self:
            required = len(lot.quality_plan_id.line_ids)
            completed = len(lot.quality_check_ids.filtered('is_measured'))
            lot.ddfsc_quality_progress = '%s / %s' % (completed, required)
            locations = lot.quant_ids.filtered(
                lambda quant: quant.quantity > 0 and quant.location_id.usage == 'internal'
            ).mapped('location_id.display_name')
            lot.ddfsc_quality_location = ', '.join(sorted(set(locations)))

    @api.model_create_multi
    def create(self, vals_list):
        lots = super().create(vals_list)
        for lot in lots.filtered('quality_plan_id'):
            lot.action_prepare_quality_checks()
        return lots

    @api.depends('product_qty')
    def _compute_ddfsc_wheat_receiving_qty(self):
        receiving = self.env.ref('ddfsc_manufacturing.loc_wheat_dock', raise_if_not_found=False)
        for lot in self:
            lot.ddfsc_wheat_receiving_qty = sum(self.env['stock.quant'].search([
                ('lot_id', '=', lot.id), ('location_id', 'child_of', receiving.id),
            ]).mapped('quantity')) if receiving else 0.0

    @api.depends('product_id')
    def _compute_quality_plan(self):
        today = fields.Date.today()
        domain = [('active', '=', True)]
        if 'approval_state' in self.env['ddfsc.quality.plan']._fields:
            domain += [
                ('approval_state', '=', 'approved'),
                '|', ('effective_from', '=', False), ('effective_from', '<=', today),
                '|', ('effective_to', '=', False), ('effective_to', '>=', today),
            ]
        plans = self.env['ddfsc.quality.plan'].search(domain, order='effective_from desc, id desc')
        for lot in self:
            lot.quality_plan_id = plans.filtered(lambda plan: lot.product_id in plan.product_ids)[:1]

    def action_prepare_quality_checks(self):
        for lot in self:
            plan = lot.quality_plan_id
            if not plan:
                raise UserError(_('No active QC plan is configured for %s.') % lot.product_id.display_name)
            existing = {check.plan_line_id: check for check in lot.quality_check_ids if check.plan_line_id}
            for line in plan.line_ids:
                values = {'check_type': line.check_type, 'apply_min': line.apply_min,
                          'standard_min': line.standard_min, 'apply_max': line.apply_max,
                          'standard_max': line.standard_max, 'note': line.note}
                if line in existing:
                    existing[line].write(values)
                else:
                    values.update({'lot_id': lot.id, 'plan_line_id': line.id})
                    self.env['ddfsc.quality.check'].create(values)
            lot._ddfsc_apply_quality_checks()
        return True

    def action_gm_approve(self):
        for lot in self:
            if not lot.ddfsc_wheat_use:
                raise UserError(_('Choose pasta, macaroni, bread, or biscuit before approval.'))
            if lot.ddfsc_quality_state != 'pass':
                raise UserError(_('The wheat sample has to pass before the general manager approves it.'))
            lot.ddfsc_gm_approved = True

    def action_release_wheat_to_general_store(self):
        self.ensure_one()
        if self.quality_checkpoint != 'incoming_wheat':
            raise UserError(_('This action is only available for incoming wheat lots.'))
        if self.ddfsc_quality_state not in ('pass', 'released'):
            raise UserError(_('The wheat lot must pass QC before it can move to General Store.'))
        source = self.env.ref('ddfsc_manufacturing.loc_wheat_dock')
        destination = self.env.ref('ddfsc_manufacturing.loc_store')
        quantity = self.ddfsc_wheat_receiving_qty
        if quantity <= 0:
            raise UserError(_('This lot has no available quantity in Wheat Receiving.'))
        existing = self.env['stock.picking'].search([
            ('state', 'not in', ('done', 'cancel')),
            ('location_id', '=', source.id), ('location_dest_id', '=', destination.id),
            ('move_line_ids.lot_id', '=', self.id),
        ], limit=1)
        if existing:
            picking = existing
        else:
            picking_type = self.env.ref('ddfsc_manufacturing.picking_type_qc_release')
            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
                'origin': _('QC release for wheat lot %s') % self.name,
            })
            move = self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': self.product_id.id,
                'product_uom_qty': quantity,
                'product_uom': self.product_id.uom_id.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
            })
            self.env['stock.move.line'].create({
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': self.product_id.id,
                'product_uom_id': self.product_id.uom_id.id,
                'quantity': quantity,
                'location_id': source.id,
                'location_dest_id': destination.id,
                'lot_id': self.id,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Release Wheat to General Store'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': picking.id,
        }

    def _ddfsc_apply_quality_checks(self):
        for lot in self:
            if lot.ddfsc_quality_state in ('released', 'rejected'):
                continue
            required = lot.quality_plan_id.line_ids
            checks = lot.quality_check_ids.filtered(lambda check: not required or check.plan_line_id in required)
            complete = bool(required) and all(line in checks.mapped('plan_line_id') for line in required)
            if any(check.result == 'fail' for check in checks):
                lot.ddfsc_quality_state = 'hold'
            elif complete and all(check.result == 'pass' for check in checks):
                lot.ddfsc_quality_state = 'pass'
            else:
                lot.ddfsc_quality_state = 'pending'

    def action_quality_hold(self):
        self.write({'ddfsc_quality_state': 'hold', 'quality_decision_by_id': self.env.user.id, 'quality_decision_date': fields.Datetime.now()})

    def action_quality_release(self):
        if self.env.ref('ddfsc_quality.group_ddfsc_quality_manager', raise_if_not_found=False) \
                and not self.env.user.has_group('ddfsc_quality.group_ddfsc_quality_manager'):
            raise UserError(_('Only a Quality Manager can authorize release by exception.'))
        if self.filtered(lambda lot: not lot.quality_release_note):
            raise UserError(_('Write a release reason before authorizing an exception.'))
        self.write({'ddfsc_quality_state': 'released', 'quality_decision_by_id': self.env.user.id, 'quality_decision_date': fields.Datetime.now()})

    def action_quality_reject(self):
        if self.filtered(lambda lot: not lot.quality_release_note):
            raise UserError(_('Write a rejection reason before rejecting the lot.'))
        self.write({'ddfsc_quality_state': 'rejected', 'quality_decision_by_id': self.env.user.id, 'quality_decision_date': fields.Datetime.now()})
