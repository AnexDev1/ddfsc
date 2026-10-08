from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

from .ddfsc_department import DEPARTMENTS


class MrpProduction(models.Model):
    _name = 'mrp.production'
    _inherit = ['mrp.production', 'ddfsc.approval.mixin']

    ddfsc_shift_id = fields.Many2one('ddfsc.shift', string='Shift', tracking=True)
    ddfsc_supervisor_id = fields.Many2one('res.users', string='Shift Supervisor', tracking=True)
    ddfsc_line_id = fields.Many2one('mrp.workcenter', string='Production Line', tracking=True)
    ddfsc_line_code = fields.Char(related='ddfsc_line_id.code')
    ddfsc_flour_request_qtl = fields.Float(
        related='ddfsc_line_id.ddfsc_flour_request_qtl',
        string='Daily Flour Request (qtl)',
    )
    conditioning_1_hours = fields.Float(string='1st Conditioning (hours)')
    conditioning_2_hours = fields.Float(string='2nd Conditioning (hours)')
    moisture_initial = fields.Float(string='Initial Moisture %')
    moisture_final = fields.Float(string='Final Moisture %')
    downtime_hours = fields.Float(string='Downtime (hours)')
    downtime_reason = fields.Selection(
        [
            ('power', 'Power cut'),
            ('film', 'Short of film'),
            ('mixer', 'Mixer'),
            ('die', 'Die'),
            ('oven', 'Oven'),
            ('packing', 'Packing machine'),
            ('other', 'Other'),
        ],
        string='Downtime Reason',
    )
    scrap_qty = fields.Float(string='Scrap Qty')
    ddfsc_maintenance_request_id = fields.Many2one(
        'maintenance.request',
        string='Maintenance Request',
        copy=False,
    )
    sweeping_qty = fields.Float(string='Sweeping Qty')
    ddfsc_loss_posted = fields.Boolean(copy=False)
    variation_qty = fields.Float(
        string='Variation',
        compute='_compute_shift_figures',
    )
    yield_ratio = fields.Float(
        string='Plan Attainment',
        compute='_compute_shift_figures',
        help='Quantity produced divided by the quantity planned on this order.',
    )
    flour_consumed_qtl = fields.Float(
        string='Flour Used (qtl)',
        compute='_compute_shift_figures',
    )
    yield_per_quintal = fields.Float(
        string='Cartons per Quintal',
        compute='_compute_shift_figures',
        help='Finished quantity divided by the quintals of flour consumed.',
    )
    wheat_consumed_qtl = fields.Float(string='Wheat Used (qtl)', compute='_compute_shift_figures')
    flour_produced_qtl = fields.Float(string='Flour Produced (qtl)', compute='_compute_shift_figures')
    byproduct_qtl = fields.Float(string='By-product (qtl)', compute='_compute_shift_figures')
    extraction_ratio = fields.Float(
        string='Extraction',
        compute='_compute_shift_figures',
        help='Flour produced divided by the wheat issued from the silo.',
    )
    bread_scrap_low = fields.Float(string='Expected Scrap From (qtl)', compute='_compute_shift_figures')
    bread_scrap_high = fields.Float(string='Expected Scrap To (qtl)', compute='_compute_shift_figures')

    @api.depends(
        'product_qty',
        'qty_produced',
        'ddfsc_line_id',
        'move_raw_ids.quantity',
        'move_raw_ids.state',
        'move_raw_ids.product_id',
        'move_finished_ids.quantity',
        'move_finished_ids.state',
        'move_finished_ids.product_id',
    )
    def _compute_shift_figures(self):
        quintal = self.env.ref('ddfsc_manufacturing.uom_quintal', raise_if_not_found=False)
        for production in self:
            production.variation_qty = production.qty_produced - production.product_qty
            production.yield_ratio = (
                production.qty_produced / production.product_qty if production.product_qty else 0.0
            )
            flour_qty = 0.0
            wheat_qty = 0.0
            flour_out = 0.0
            byproduct = 0.0
            if quintal:
                for move in production.move_raw_ids.filtered(lambda item: item.state == 'done'):
                    qty = move.product_uom._compute_quantity(move.quantity, quintal)
                    if move.product_id.ddfsc_is_flour:
                        flour_qty += qty
                    if move.product_id == self.env.ref('ddfsc_manufacturing.product_wheat').product_variant_id:
                        wheat_qty += qty
                for move in production.move_finished_ids.filtered(lambda item: item.state == 'done'):
                    qty = move.product_uom._compute_quantity(move.quantity, quintal)
                    if move.product_id.ddfsc_is_flour:
                        flour_out += qty
                    if move.product_id.ddfsc_is_byproduct:
                        byproduct += qty
            production.flour_consumed_qtl = flour_qty
            production.yield_per_quintal = production.qty_produced / flour_qty if flour_qty else 0.0
            production.wheat_consumed_qtl = wheat_qty
            production.flour_produced_qtl = flour_out
            production.byproduct_qtl = byproduct
            production.extraction_ratio = flour_out / wheat_qty if wheat_qty else 0.0
            production.bread_scrap_low = flour_qty * 0.1
            production.bread_scrap_high = flour_qty * 0.2

    @api.constrains('ddfsc_line_id', 'ddfsc_shift_id', 'date_start', 'state')
    def _check_one_order_per_line_shift(self):
        for production in self:
            if production.state == 'cancel' or not production.ddfsc_line_id or not production.ddfsc_shift_id or not production.date_start:
                continue
            day = fields.Datetime.context_timestamp(production, production.date_start).date()
            others = self.search([
                ('id', '!=', production.id),
                ('state', '!=', 'cancel'),
                ('ddfsc_line_id', '=', production.ddfsc_line_id.id),
                ('ddfsc_shift_id', '=', production.ddfsc_shift_id.id),
                ('date_start', '!=', False),
            ])
            for other in others:
                other_day = fields.Datetime.context_timestamp(other, other.date_start).date()
                if other_day == day:
                    raise ValidationError(_(
                        '%(line)s already has %(shift)s on %(day)s (%(order)s). '
                        'Use another shift or cancel that order.',
                        line=production.ddfsc_line_id.display_name,
                        shift=production.ddfsc_shift_id.display_name,
                        day=day,
                        order=other.display_name,
                    ))

    @api.constrains('conditioning_1_hours', 'conditioning_2_hours', 'ddfsc_line_id')
    def _check_conditioning_only_on_mill(self):
        for production in self:
            if production.ddfsc_line_id.code == 'MILL':
                continue
            if production.conditioning_1_hours or production.conditioning_2_hours:
                raise ValidationError(_('First and second conditioning are recorded on the flour mill only.'))

    def _ddfsc_approval_role(self):
        self.ensure_one()
        return 'operation'

    ddfsc_picking_ids = fields.One2many(
        'stock.picking',
        'ddfsc_production_id',
        string='Plant Transfers',
    )
    ddfsc_picking_count = fields.Integer(compute='_compute_ddfsc_document_counts')

    @api.depends('ddfsc_picking_ids')
    def _compute_ddfsc_document_counts(self):
        for production in self:
            production.ddfsc_picking_count = len(production.ddfsc_picking_ids.filtered(
                lambda picking: picking.state != 'cancel'
            ))

    def action_view_ddfsc_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Plant Transfers'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('ddfsc_production_id', '=', self.id), ('state', '!=', 'cancel')],
            'context': {'default_ddfsc_production_id': self.id},
        }

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        department = self.env.user.ddfsc_department
        if department:
            line = self._ddfsc_line_for_department(department)
            if line:
                values['ddfsc_line_id'] = line.id
        elif not values.get('ddfsc_line_id') and self.env.context.get('ddfsc_department'):
            line = self._ddfsc_line_for_department(self.env.context['ddfsc_department'])
            if line:
                values['ddfsc_line_id'] = line.id
        line = self.env['mrp.workcenter'].browse(values.get('ddfsc_line_id') or False).exists()
        if line:
            source, destination = self._ddfsc_locations_for_code(line.code)
            if source and destination:
                values['location_src_id'] = source.id
                values['location_dest_id'] = destination.id
        return values

    @api.model
    def _ddfsc_line_for_department(self, department):
        code = DEPARTMENTS.get(department, {}).get('line')
        if not code:
            return self.env['mrp.workcenter']
        return self.env['mrp.workcenter'].search([('code', '=', code)], limit=1)

    @api.model
    def _ddfsc_locations_for_code(self, code):
        locations = {
            # (component location, finished / temp output location)
            'MILL': ('loc_mill', 'loc_flour'),
            'PASTA': ('loc_pasta', 'loc_pasta_finished'),
            'MAC': ('loc_macaroni', 'loc_macaroni_finished'),
            'BREAD': ('loc_bread', 'loc_bread'),
            'BISC-CN': ('loc_biscuit', 'loc_biscuit'),
            'BISC-OR': ('loc_biscuit', 'loc_biscuit'),
        }
        pair = locations.get(code)
        if not pair:
            return self.env['stock.location'], self.env['stock.location']
        return (
            self.env.ref('ddfsc_manufacturing.%s' % pair[0]),
            self.env.ref('ddfsc_manufacturing.%s' % pair[1]),
        )

    @api.depends('picking_type_id', 'ddfsc_line_id')
    def _compute_locations(self):
        super()._compute_locations()
        for production in self.filtered(lambda item: item.state == 'draft'):
            source, destination = production._ddfsc_plant_locations()
            if source and destination:
                production.location_src_id = source
                production.location_dest_id = destination

    def _ddfsc_plant_locations(self):
        self.ensure_one()
        return self._ddfsc_locations_for_code(self.ddfsc_line_id.code)

    def _ddfsc_wheat_silo(self):
        self.ensure_one()
        data = self.env['ir.model.data'].search([
            ('module', '=', 'ddfsc_manufacturing'),
            ('model', '=', 'product.template'),
            ('res_id', '=', self.product_id.product_tmpl_id.id),
        ], limit=1)
        silos = {
            'product_flour_g1': 'loc_silo_bread',
            'product_bread_market': 'loc_silo_bread',
            'product_bread_university': 'loc_silo_bread',
            'product_flour_g2': 'loc_silo_biscuit',
            'product_zebib': 'loc_silo_biscuit',
            'product_defense': 'loc_silo_biscuit',
            'product_flour_scp': 'loc_silo_macaroni',
            'product_pasta_short': 'loc_silo_macaroni',
            'product_flour_lcp': 'loc_silo_pasta',
            'product_pasta_long': 'loc_silo_pasta',
        }
        xmlid = silos.get(data.name, 'loc_silo_pasta')
        return self.env.ref('ddfsc_manufacturing.%s' % xmlid)

    def _ddfsc_product_xmlid(self):
        self.ensure_one()
        return self.env['ir.model.data'].search([
            ('module', '=', 'ddfsc_manufacturing'),
            ('model', '=', 'product.template'),
            ('res_id', '=', self.product_id.product_tmpl_id.id),
        ], limit=1).name

    def _ddfsc_guess_line(self):
        self.ensure_one()
        codes = {
            'product_flour_g1': 'MILL',
            'product_flour_g2': 'MILL',
            'product_flour_scp': 'MILL',
            'product_flour_lcp': 'MILL',
            'product_bread_market': 'BREAD',
            'product_bread_university': 'BREAD',
            'product_pasta_long': 'PASTA',
            'product_pasta_short': 'MAC',
        }
        code = codes.get(self._ddfsc_product_xmlid())
        if not code:
            return self.env['mrp.workcenter']
        return self.env['mrp.workcenter'].search([('code', '=', code)], limit=1)

    def action_confirm(self):
        draft = self.filtered(lambda production: production.state == 'draft')
        for production in draft.filtered(lambda item: not item.ddfsc_line_id):
            line = production._ddfsc_guess_line()
            if line:
                production.ddfsc_line_id = line
        for production in draft:
            source, destination = production._ddfsc_plant_locations()
            if not source or not destination:
                continue
            production.write({
                'location_src_id': source.id,
                'location_dest_id': destination.id,
            })
            production.move_raw_ids.filtered(
                lambda move: move.state not in ('done', 'cancel')
            ).write({'location_id': source.id})
            finished = production.move_finished_ids.filtered(
                lambda move: move.state not in ('done', 'cancel')
            )
            if production.ddfsc_line_id.code == 'MILL':
                mill = self.env.ref('ddfsc_manufacturing.loc_mill')
                finished.filtered('product_id.ddfsc_is_byproduct').write({'location_dest_id': mill.id})
                finished.filtered(lambda move: not move.product_id.ddfsc_is_byproduct).write({
                    'location_dest_id': destination.id,
                })
            else:
                finished.write({'location_dest_id': destination.id})
        result = super().action_confirm()
        return result

    def button_mark_done(self):
        self._ddfsc_ensure_approved()
        mill = self.env.ref('ddfsc_manufacturing.loc_mill', raise_if_not_found=False)
        for production in self.filtered(lambda item: item.ddfsc_line_id.code == 'MILL' and mill):
            production.move_finished_ids.filtered(
                lambda move: move.product_id.ddfsc_is_byproduct and move.state not in ('done', 'cancel')
            ).write({'location_dest_id': mill.id})
        res = super().button_mark_done()
        if res is True:
            self._ddfsc_post_losses()
        return res

    def _ddfsc_post_losses(self):
        for production in self.filtered(lambda item: item.state == 'done' and not item.ddfsc_loss_posted):
            lot = production.lot_producing_ids[:1]
            for quantity, label in ((production.scrap_qty, 'Scrap'), (production.sweeping_qty, 'Sweeping')):
                if not quantity:
                    continue
                if production.product_id.tracking != 'none' and not lot:
                    raise UserError(_('Set the finished lot before posting scrap or sweeping.'))
                if production.ddfsc_line_id.code in ('PASTA', 'MAC'):
                    production._ddfsc_recycle(quantity, lot, label)
                    continue
                scrap = self.env['stock.scrap'].create({
                    'product_id': production.product_id.id,
                    'scrap_qty': quantity,
                    'product_uom_id': production.product_uom_id.id,
                    'location_id': production.location_dest_id.id,
                    'lot_id': lot.id if lot else False,
                    'origin': '%s %s' % (label, production.name),
                })
                scrap.do_scrap()
            production.ddfsc_loss_posted = True

    def _ddfsc_recycle(self, quantity, lot, label):
        self.ensure_one()
        recycle = self.env.ref('ddfsc_manufacturing.loc_recycle')
        move = self.env['stock.move'].create({
            'product_id': self.product_id.id,
            'product_uom_qty': quantity,
            'product_uom': self.product_uom_id.id,
            'location_id': self.location_dest_id.id,
            'location_dest_id': recycle.id,
            'origin': '%s %s' % (label, self.name),
            'picked': True,
            'move_line_ids': [Command.create({
                'product_id': self.product_id.id,
                'product_uom_id': self.product_uom_id.id,
                'quantity': quantity,
                'location_id': self.location_dest_id.id,
                'location_dest_id': recycle.id,
                'lot_id': lot.id if lot else False,
            })],
        })
        move._action_done()

    def action_log_downtime(self):
        """Open a corrective request for mixer, die, oven, or packing downtime."""
        self.ensure_one()
        if self.ddfsc_maintenance_request_id:
            return self._maintenance_request_action(self.ddfsc_maintenance_request_id)
        equipment_reasons = ('mixer', 'die', 'oven', 'packing')
        if self.downtime_reason not in equipment_reasons:
            raise UserError(_(
                'A maintenance request is opened for mixer, die, oven, or packing downtime. '
                'Power cuts and film shortages stay on the shift report.'
            ))
        if not self.ddfsc_line_id:
            raise UserError(_('Choose the production line before logging this downtime.'))
        equipment = self.env['maintenance.equipment'].search([
            ('ddfsc_workcenter_id', '=', self.ddfsc_line_id.id),
            ('ddfsc_downtime_code', '=', self.downtime_reason),
        ], limit=1)
        if not equipment:
            raise UserError(_(
                'No %(reason)s is registered on %(line)s.',
                reason=dict(self._fields['downtime_reason'].selection).get(self.downtime_reason),
                line=self.ddfsc_line_id.display_name,
            ))
        reason = dict(self._fields['downtime_reason'].selection).get(self.downtime_reason)
        request = self.env['maintenance.request'].create({
            'name': '%s downtime on %s' % (reason, self.name),
            'equipment_id': equipment.id,
            'maintenance_team_id': equipment.maintenance_team_id.id,
            'maintenance_type': 'corrective',
            'description': '<p>%s hours. Shift %s.</p>' % (
                self.downtime_hours or 0,
                self.ddfsc_shift_id.name or '',
            ),
        })
        self.ddfsc_maintenance_request_id = request
        return self._maintenance_request_action(request)

    def _maintenance_request_action(self, request):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Maintenance Request'),
            'res_model': 'maintenance.request',
            'view_mode': 'form',
            'res_id': request.id,
        }
