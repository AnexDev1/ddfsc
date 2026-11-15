import json
from datetime import timedelta

import pytz

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

from .ddfsc_department import DEPARTMENTS, department_for_line
from .ddfsc_shift import factory_tz


class MrpProduction(models.Model):
    _name = 'mrp.production'
    _inherit = ['mrp.production', 'ddfsc.approval.mixin']

    # copy=False: a backorder or duplicate is produced in its own shift, with its own figures.
    ddfsc_shift_id = fields.Many2one('ddfsc.shift', string='Shift', tracking=True, copy=False)
    ddfsc_supervisor_id = fields.Many2one('res.users', string='Shift Supervisor', tracking=True, copy=False)
    ddfsc_production_date = fields.Date(
        string='Production Day', compute='_compute_ddfsc_production_date', store=True, index=True,
        help='The factory day this order belongs to. A night shift that runs past midnight '
             '(22:00-06:00) belongs to the day it started.',
    )
    ddfsc_line_id = fields.Many2one('mrp.workcenter', string='Production Line', tracking=True)
    ddfsc_line_code = fields.Char(related='ddfsc_line_id.code')
    ddfsc_department = fields.Selection(
        selection=lambda self: [(key, value['label']) for key, value in DEPARTMENTS.items()],
        compute='_compute_ddfsc_department', store=True, index=True,
        string='Department',
    )
    ddfsc_workflow_state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('waiting_approval', 'Waiting Approval'),
            ('approved', 'Approved'),
            ('done', 'Done'),
            ('needs_changes', 'Needs Changes'),
            ('cancel', 'Cancelled'),
        ],
        string='Production Workflow',
        compute='_compute_ddfsc_workflow_state',
    )
    ddfsc_flour_request_qtl = fields.Float(
        related='ddfsc_line_id.ddfsc_flour_request_qtl',
        string='Daily Flour Request (qtl)',
    )
    conditioning_1_hours = fields.Float(string='1st Conditioning (hours)', copy=False)
    conditioning_2_hours = fields.Float(string='2nd Conditioning (hours)', copy=False)
    moisture_initial = fields.Float(string='Initial Moisture %', copy=False)
    moisture_final = fields.Float(string='Final Moisture %', copy=False)
    downtime_hours = fields.Float(string='Downtime (hours)', copy=False)
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
        copy=False,
    )
    scrap_qty = fields.Float(string='Saleable Breakage', copy=False)
    ddfsc_breakage_uom = fields.Char(string='Breakage Unit', compute='_compute_ddfsc_breakage_uom')
    ddfsc_maintenance_request_id = fields.Many2one(
        'maintenance.request',
        string='Maintenance Request',
        copy=False,
    )
    sweeping_qty = fields.Float(
        string='Sweepings / Waste (kg)',
        copy=False,
        help='Floor sweepings or contaminated material, weighed in kg. Recorded as a loss on '
             'the shift report; it never removes finished goods from stock.',
    )
    ddfsc_loss_posted = fields.Boolean(copy=False)
    ddfsc_variance_reason = fields.Text(
        string='Variance Explanation',
        copy=False,
        tracking=True,
        help='Required when any ingredient is used above or below the line tolerance.',
    )
    ddfsc_variance_tolerance = fields.Float(
        related='ddfsc_line_id.ddfsc_variance_tolerance', string='Variance Tolerance %',
    )
    ddfsc_variance_exceeded = fields.Boolean(
        string='Variance Above Tolerance', compute='_compute_ddfsc_variance_exceeded',
    )
    ddfsc_approval_fingerprint = fields.Text(copy=False, readonly=True)
    mill_unaccounted_qtl = fields.Float(
        string='Unaccounted Loss / Gain (qtl)', compute='_compute_shift_figures',
        help='Wheat used minus flour, by-product and sweepings. Positive is unexplained loss; '
             'negative means the output weighs more than the wheat (for example added water).',
    )
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
    # Stored shift figures: Odoo's qty_produced is not stored, so reports that
    # group by day and shift (list totals, pivot, graph) need their own copy.
    ddfsc_output_qty = fields.Float(
        string='Produced', compute='_compute_ddfsc_shift_totals', store=True, digits='Product Unit',
    )
    ddfsc_shortfall_qty = fields.Float(
        string='Variation vs Target', compute='_compute_ddfsc_shift_totals', store=True, digits='Product Unit',
        help='Produced minus target. Negative means the shift made less than planned.',
    )
    ddfsc_flour_used_qtl = fields.Float(
        string='Flour Used (qtl)', compute='_compute_ddfsc_shift_totals', store=True, digits='Product Unit',
    )
    ddfsc_variance_snapshot_taken = fields.Boolean(copy=False, readonly=True)
    ddfsc_planned_output_qty = fields.Float(string='Planned Output', copy=False, readonly=True)
    ddfsc_actual_output_qty = fields.Float(string='Actual Output', compute='_compute_output_variance')
    ddfsc_output_variance_qty = fields.Float(string='Output Variance', compute='_compute_output_variance')
    ddfsc_output_variance_percent = fields.Float(string='Output Variance %', compute='_compute_output_variance')
    ddfsc_variance_line_ids = fields.One2many(
        'ddfsc.production.variance.line', 'production_id', string='Planned vs Actual Consumption',
    )

    @api.depends('product_qty', 'move_finished_ids.state', 'move_finished_ids.quantity',
                 'move_finished_ids.product_id', 'move_raw_ids.state', 'move_raw_ids.quantity',
                 'move_raw_ids.product_id')
    def _compute_ddfsc_shift_totals(self):
        quintal = self.env.ref('ddfsc_manufacturing.uom_quintal', raise_if_not_found=False)
        for production in self:
            finished = production.move_finished_ids.filtered(
                lambda move: move.state == 'done' and move.product_id == production.product_id)
            produced = sum(
                move.product_uom._compute_quantity(move.quantity, production.product_uom_id)
                for move in finished
            )
            flour = sum(
                move.product_uom._compute_quantity(move.quantity, quintal)
                for move in production.move_raw_ids
                if quintal and move.state == 'done' and move.product_id.ddfsc_is_flour
            )
            production.ddfsc_output_qty = produced
            production.ddfsc_shortfall_qty = produced - production.product_qty if production.state == 'done' else 0.0
            production.ddfsc_flour_used_qtl = flour

    @api.depends('ddfsc_planned_output_qty', 'product_qty', 'qty_produced')
    def _compute_output_variance(self):
        for production in self:
            planned = production.ddfsc_planned_output_qty or production.product_qty
            actual = production.qty_produced
            production.ddfsc_actual_output_qty = actual
            production.ddfsc_output_variance_qty = actual - planned
            production.ddfsc_output_variance_percent = (
                ((actual - planned) / planned) * 100 if planned else 0.0
            )

    @api.depends('ddfsc_line_id', 'ddfsc_line_id.code')
    def _compute_ddfsc_department(self):
        for production in self:
            production.ddfsc_department = department_for_line(production.ddfsc_line_id.code)

    @api.depends('ddfsc_line_id.code')
    def _compute_ddfsc_breakage_uom(self):
        for production in self:
            product = production._ddfsc_saleable_byproduct() if production.ddfsc_line_id else False
            production.ddfsc_breakage_uom = product.uom_id.name if product else production.product_uom_id.name

    @api.depends('ddfsc_variance_line_ids.variance_percent', 'ddfsc_variance_line_ids.is_unplanned',
                 'ddfsc_line_id.ddfsc_variance_tolerance')
    def _compute_ddfsc_variance_exceeded(self):
        for production in self:
            production.ddfsc_variance_exceeded = bool(production._ddfsc_variances_over_tolerance())

    def _ddfsc_variances_over_tolerance(self):
        """Variance lines outside the line tolerance (unplanned use always counts)."""
        self.ensure_one()
        tolerance = self.ddfsc_line_id.ddfsc_variance_tolerance
        lines = self.sudo().ddfsc_variance_line_ids
        return lines.filtered(
            lambda line: (line.is_unplanned and line.actual_qty)
            or (not line.is_unplanned and abs(line.variance_percent) > tolerance + 1e-9)
        )

    @api.depends('state', 'ddfsc_approval_state')
    def _compute_ddfsc_workflow_state(self):
        """Present one operator-facing workflow instead of two unrelated bars."""
        for production in self:
            if production.state == 'cancel':
                production.ddfsc_workflow_state = 'cancel'
            elif production.state == 'done':
                production.ddfsc_workflow_state = 'done'
            elif production.ddfsc_approval_state == 'refused':
                production.ddfsc_workflow_state = 'needs_changes'
            elif production.ddfsc_approval_state == 'submitted':
                production.ddfsc_workflow_state = 'waiting_approval'
            elif production.ddfsc_approval_state == 'approved':
                production.ddfsc_workflow_state = 'approved'
            elif production.state in ('confirmed', 'progress', 'to_close'):
                production.ddfsc_workflow_state = 'confirmed'
            else:
                production.ddfsc_workflow_state = 'draft'

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
        'sweeping_qty',
    )
    def _compute_shift_figures(self):
        quintal = self.env.ref('ddfsc_manufacturing.uom_quintal', raise_if_not_found=False)
        wheat_template = self.env.ref('ddfsc_manufacturing.product_wheat', raise_if_not_found=False)
        wheat_product = wheat_template.product_variant_id if wheat_template else self.env['product.product']
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
                    if move.product_id == wheat_product:
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
            # Mill mass balance: sweepings are weighed in kg (1 qtl = 100 kg).
            production.mill_unaccounted_qtl = (
                wheat_qty - flour_out - byproduct - (production.sweeping_qty or 0.0) / 100.0
                if wheat_qty else 0.0
            )

    @api.constrains('ddfsc_line_id', 'ddfsc_shift_id', 'date_start', 'state', 'ddfsc_production_date')
    def _check_one_order_per_line_shift(self):
        for production in self:
            if production.state == 'cancel' or not production.ddfsc_line_id or not production.ddfsc_shift_id or not production.date_start:
                continue
            day = production.ddfsc_production_date or production._ddfsc_production_day()
            # sudo: the clash must be found even on an order another user cannot see.
            others = self.sudo().search([
                ('id', '!=', production.id),
                ('state', '!=', 'cancel'),
                ('ddfsc_line_id', '=', production.ddfsc_line_id.id),
                ('ddfsc_shift_id', '=', production.ddfsc_shift_id.id),
                ('date_start', '>=', production.date_start - timedelta(days=2)),
                ('date_start', '<=', production.date_start + timedelta(days=2)),
            ])
            for other in others:
                if production.production_group_id and other.production_group_id == production.production_group_id:
                    continue  # a backorder of the same order, not a second order
                if (other.ddfsc_production_date or other._ddfsc_production_day()) == day:
                    raise ValidationError(_(
                        '%(line)s already has %(shift)s on %(day)s (%(order)s). '
                        'Use another shift or cancel that order.',
                        line=production.ddfsc_line_id.display_name,
                        shift=production.ddfsc_shift_id.display_name,
                        day=day,
                        order=other.display_name,
                    ))

    @api.depends('date_start', 'ddfsc_shift_id', 'ddfsc_shift_id.hour_from', 'ddfsc_shift_id.hour_to',
                 'company_id')
    def _compute_ddfsc_production_date(self):
        for production in self:
            production.ddfsc_production_date = (
                production._ddfsc_production_day() if production.date_start else False
            )

    def _get_backorder_mo_vals(self):
        values = super()._get_backorder_mo_vals()
        # The remaining quantity is made in a later shift: the operator chooses it.
        values.update({'ddfsc_shift_id': False, 'ddfsc_supervisor_id': False})
        return values

    def _ddfsc_production_day(self):
        """The production day a shift belongs to, in factory time.

        A night shift that crosses midnight (22:00-06:00) belongs to the day it
        started: an order started at 01:00 is still the previous day's Shift 3.
        Factory time is used for everyone, whatever timezone a user has set.
        """
        self.ensure_one()
        local = pytz.utc.localize(self.date_start).astimezone(factory_tz(self.env, self.company_id))
        shift = self.ddfsc_shift_id
        hour = local.hour + local.minute / 60.0
        if shift and shift.hour_to <= shift.hour_from and hour < shift.hour_to:
            return (local - timedelta(days=1)).date()
        return local.date()

    @api.onchange('ddfsc_shift_id')
    def _onchange_ddfsc_shift_id(self):
        """Keep the start time inside the chosen shift on the same production day."""
        for production in self:
            shift = production.ddfsc_shift_id
            if not shift or production.state not in (False, 'draft', 'confirmed'):
                continue
            if not production.date_start:
                continue
            local = pytz.utc.localize(production.date_start).astimezone(
                factory_tz(self.env, production.company_id))
            hour = local.hour + local.minute / 60.0
            if shift._contains_hour(hour):
                continue
            current, day = self.env['ddfsc.shift']._shift_at(production.date_start, production.company_id)
            production.date_start = shift._start_on(day, production.company_id)

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
    ddfsc_quality_lot_ids = fields.Many2many('stock.lot', compute='_compute_ddfsc_quality_lots')
    ddfsc_quality_lot_count = fields.Integer(compute='_compute_ddfsc_quality_lots')

    @api.depends('ddfsc_picking_ids')
    def _compute_ddfsc_document_counts(self):
        for production in self:
            production.ddfsc_picking_count = len(production.ddfsc_picking_ids.filtered(
                lambda picking: picking.state != 'cancel'
            ))

    @api.depends('lot_producing_ids', 'move_finished_ids.move_line_ids.lot_id')
    def _compute_ddfsc_quality_lots(self):
        for production in self:
            lots = production.lot_producing_ids | production.move_finished_ids.move_line_ids.lot_id
            lots = lots.filtered(lambda lot: lot.product_id == production.product_id)
            production.ddfsc_quality_lot_ids = lots
            production.ddfsc_quality_lot_count = len(lots)

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
        """Open the standalone QC document, never the legacy lot form.

        Manufacturing remains installable without ddfsc_quality, so retain a
        false return as a compatibility fallback for that optional module.
        """
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

    def _ddfsc_quality_redirect_action(self):
        """Action used by RedirectWarning's button when QC blocks an FG move."""
        return self.env.ref(
            'ddfsc_quality.action_qc_inspection_document',
            raise_if_not_found=False,
        ) or self.env.ref('ddfsc_manufacturing.action_ddfsc_qc_lots')

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
        # Menu context wins so Bread / Biscuit / Pasta menus set the right line.
        department = self.env.context.get('ddfsc_department') or self.env.user.ddfsc_department
        if department and not values.get('ddfsc_line_id'):
            line = self._ddfsc_line_for_department(department)
            if line:
                values['ddfsc_line_id'] = line.id
        # Default to the shift running now, in factory time, and its supervisor.
        if 'ddfsc_shift_id' in fields_list and not values.get('ddfsc_shift_id'):
            shift, _day = self.env['ddfsc.shift']._shift_at()
            if shift:
                values['ddfsc_shift_id'] = shift.id
        if 'ddfsc_supervisor_id' in fields_list and not values.get('ddfsc_supervisor_id'):
            values['ddfsc_supervisor_id'] = self.env.user.id
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
            # (component / floor location, temp finished location)
            'MILL': ('loc_mill', 'loc_flour_finished'),
            'PASTA': ('loc_pasta', 'loc_pasta_finished'),
            'MAC': ('loc_macaroni', 'loc_macaroni_finished'),
            'BREAD': ('loc_bread', 'loc_bread_finished'),
            'BISC-CN': ('loc_biscuit', 'loc_biscuit_finished'),
            'BISC-OR': ('loc_biscuit', 'loc_biscuit_finished'),
        }
        pair = locations.get(code)
        if not pair:
            return self.env['stock.location'], self.env['stock.location']
        source = self.env.ref('ddfsc_manufacturing.%s' % pair[0], raise_if_not_found=False)
        destination = self.env.ref('ddfsc_manufacturing.%s' % pair[1], raise_if_not_found=False)
        return source or self.env['stock.location'], destination or self.env['stock.location']

    @api.depends('picking_type_id', 'ddfsc_line_id')
    def _compute_locations(self):
        super()._compute_locations()
        productions = self.with_context(skip_compute_move_raw_ids=True).filtered(
            lambda item: item.state == 'draft'
        )
        for production in productions:
            source, destination = production._ddfsc_plant_locations()
            if source and destination:
                production.location_src_id = source
                production.location_dest_id = destination

    @api.onchange('product_id', 'bom_id')
    def _onchange_ddfsc_product_locations(self):
        for production in self:
            if production.state and production.state != 'draft':
                continue
            line = production._ddfsc_guess_line()
            if line:
                production.ddfsc_line_id = line
            source, destination = production._ddfsc_plant_locations()
            if source and destination:
                production.with_context(skip_compute_move_raw_ids=True).update({
                    'location_src_id': source.id,
                    'location_dest_id': destination.id,
                })

    def _ddfsc_plant_locations(self):
        self.ensure_one()
        if not self.ddfsc_line_id:
            return self.env['stock.location'], self.env['stock.location']
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
            'product_zebib': 'BISC-CN',
            'product_defense': 'BISC-CN',
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
            production._ddfsc_remove_orphan_raw_moves()
            source, destination = production._ddfsc_plant_locations()
            if not source or not destination:
                continue
            # Skip recompute: rewriting location_src_id rebuilds components and can duplicate lines.
            production.with_context(skip_compute_move_raw_ids=True).write({
                'location_src_id': source.id,
                'location_dest_id': destination.id,
            })
            production.move_raw_ids.filtered(
                lambda move: move.state not in ('done', 'cancel')
            ).write({'location_id': source.id})
            finished = production.move_finished_ids.filtered(
                lambda move: move.state not in ('done', 'cancel')
            )
            byproduct_loc = production._ddfsc_byproduct_location()
            if byproduct_loc:
                finished.filtered('product_id.ddfsc_is_byproduct').write({
                    'location_dest_id': byproduct_loc.id,
                })
            finished.filtered(lambda move: not move.product_id.ddfsc_is_byproduct).write({
                'location_dest_id': destination.id,
            })
        result = super().action_confirm()
        self._ddfsc_sync_variance_lines(snapshot_plan=True)
        return result

    def _ddfsc_remove_orphan_raw_moves(self):
        """Drop manual duplicates left after BoM lines were recreated on upgrade."""
        self.ensure_one()
        if self.state != 'draft':
            return
        bom_products = self.move_raw_ids.filtered('bom_line_id').mapped('product_id')
        orphans = self.move_raw_ids.filtered(
            lambda move: not move.bom_line_id
            and move.product_id in bom_products
            and move.state not in ('done', 'cancel')
        )
        if orphans:
            orphans._action_cancel()
            orphans.unlink()

    # ------------------------------------------------------------------
    # Approval: the manager approves figures, not just a document
    # ------------------------------------------------------------------
    def _ddfsc_fingerprint(self):
        """Figures the operation manager approves.  Any change re-opens approval."""
        self.ensure_one()
        raw = sorted(
            (move.product_id.id, round(move.quantity, 4))
            for move in self.move_raw_ids if move.state != 'cancel'
        )
        finished = sorted(
            (move.product_id.id, round(move.quantity, 4))
            for move in self.move_finished_ids
            if move.state != 'cancel' and move.product_id != self.product_id
        )
        return json.dumps({
            'producing': round(self.qty_producing, 4),
            'raw': raw,
            'byproducts': finished,
            'breakage': round(self.scrap_qty or 0.0, 4),
            'sweepings': round(self.sweeping_qty or 0.0, 4),
        }, sort_keys=True)

    def _ddfsc_fingerprint_changes(self):
        """Human-readable list of figures changed since approval."""
        self.ensure_one()
        try:
            before = json.loads(self.ddfsc_approval_fingerprint or '{}')
        except ValueError:
            return [_('approved figures could not be read')]
        after = json.loads(self._ddfsc_fingerprint())
        if before == after:
            return []
        Product = self.env['product.product'].sudo()
        changes = []
        if before.get('producing') != after.get('producing'):
            changes.append(_('Quantity produced %(a)s → %(b)s', a=before.get('producing'), b=after.get('producing')))
        for key, label in (('raw', _('consumed')), ('byproducts', _('by-product'))):
            old = dict(map(tuple, before.get(key, [])))
            new = dict(map(tuple, after.get(key, [])))
            for product_id in sorted(set(old) | set(new)):
                if old.get(product_id) != new.get(product_id):
                    changes.append('%s %s %s → %s' % (
                        Product.browse(product_id).display_name, label,
                        old.get(product_id, 0), new.get(product_id, 0)))
        for key, label in (('breakage', _('Breakage')), ('sweepings', _('Sweepings'))):
            if before.get(key) != after.get(key):
                changes.append('%s %s → %s' % (label, before.get(key), after.get(key)))
        return changes

    def action_ddfsc_submit(self):
        for production in self:
            if production.state in ('draft', 'cancel', 'done'):
                raise UserError(_('Confirm the order and record production before submitting it for approval.'))
            if not production.ddfsc_shift_id:
                raise UserError(_('Choose the shift on the Shift Report tab before submitting %s.', production.display_name))
            production._ddfsc_sync_variance_lines()
            over = production._ddfsc_variances_over_tolerance()
            if over and not (production.ddfsc_variance_reason or '').strip():
                details = '\n'.join(
                    '• %s: standard %.3f, actual %.3f %s (%+.1f%%)' % (
                        line.product_id.display_name, line.expected_qty, line.actual_qty,
                        line.uom_id.name, line.variance_percent,
                    ) if not line.is_unplanned else '• %s: %.3f %s used but not in the recipe' % (
                        line.product_id.display_name, line.actual_qty, line.uom_id.name)
                    for line in over
                )
                raise UserError(_(
                    'Consumption is outside the %(tol)s%% tolerance for %(line)s:\n%(details)s\n\n'
                    'Write the reason in "Variance Explanation" (Shift Report tab), then submit again.',
                    tol=production.ddfsc_variance_tolerance, line=production.ddfsc_line_id.display_name,
                    details=details,
                ))
        result = super().action_ddfsc_submit()
        for production in self:
            production._ddfsc_post_variance_summary(_('Submitted for approval'))
        return result

    def action_ddfsc_approve(self):
        result = super().action_ddfsc_approve()
        for production in self:
            production.sudo().ddfsc_approval_fingerprint = production._ddfsc_fingerprint()
        return result

    def action_ddfsc_reset(self):
        result = super().action_ddfsc_reset()
        self.sudo().write({'ddfsc_approval_fingerprint': False})
        return result

    def _ddfsc_post_variance_summary(self, title):
        """Write the variance table into the chatter so it stays in the audit trail."""
        self.ensure_one()
        lines = self.sudo().ddfsc_variance_line_ids
        if not lines:
            return
        rows = Markup('').join(
            Markup('<tr><td>%s</td><td style="text-align:right">%.3f</td><td style="text-align:right">%.3f</td>'
                   '<td style="text-align:right">%+.3f</td><td style="text-align:right">%+.1f%%</td><td>%s</td></tr>') % (
                line.product_id.display_name, line.expected_qty, line.actual_qty,
                line.variance_qty, line.variance_percent, line.uom_id.name,
            ) for line in lines
        )
        reason = self.ddfsc_variance_reason
        body = Markup(
            '<b>%s</b><br/>Output: planned %.3f, produced %.3f %s'
            '<table class="table table-sm o_mrp_variance"><tr><th>Material</th><th>Standard</th>'
            '<th>Actual</th><th>Variance</th><th>%%</th><th>Unit</th></tr>%s</table>%s'
        ) % (
            title, self.ddfsc_planned_output_qty or self.product_qty,
            self.qty_producing or self.qty_produced, self.product_uom_id.name, rows,
            Markup('<b>Explanation:</b> %s') % reason if reason else '',
        )
        self.message_post(body=body)

    def button_mark_done(self):
        self._ddfsc_ensure_approved()
        # The consumption-warning and backorder wizards call Mark Done a second
        # time after Odoo itself has filled by-product quantities: that is the
        # same completion, not an edit, so the comparison runs on the first call.
        resumed = self.env.context.get('skip_consumption') or self.env.context.get('skip_backorder')
        changed = {} if resumed else {
            production: production._ddfsc_fingerprint_changes()
            for production in self
            if production._ddfsc_approval_role() and production.ddfsc_approval_fingerprint
        }
        changed = {production: changes for production, changes in changed.items() if changes}
        if changed:
            # Figures moved after the manager approved them: send the order
            # back for approval instead of completing it silently.
            for production, changes in changed.items():
                production.write({'ddfsc_approval_state': 'draft', 'ddfsc_approved_uid': False,
                                  'ddfsc_approval_date': False})
                production.sudo().ddfsc_approval_fingerprint = False
                production.message_post(body=Markup('<b>%s</b><ul>%s</ul>') % (
                    _('Figures changed after approval — approval withdrawn'),
                    Markup('').join(Markup('<li>%s</li>') % change for change in changes),
                ))
            names = ', '.join(production.display_name for production in changed)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Approval needed again'),
                    'message': _('%s changed after the operation manager approved it. '
                                 'Submit it for approval again.', names),
                    'type': 'warning',
                    'sticky': True,
                    'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
                },
            }
        for production in self:
            source, destination = production._ddfsc_plant_locations()
            finished = production.move_finished_ids.filtered(
                lambda move: move.state not in ('done', 'cancel')
            )
            if not destination:
                continue
            production.location_dest_id = destination
            byproduct_loc = production._ddfsc_byproduct_location()
            if byproduct_loc:
                finished.filtered('product_id.ddfsc_is_byproduct').write({
                    'location_dest_id': byproduct_loc.id,
                })
            finished.filtered(lambda move: not move.product_id.ddfsc_is_byproduct).write({
                'location_dest_id': destination.id,
            })
        res = super().button_mark_done()
        # Odoo returns an action (backorder, report, wizard) as often as True;
        # post figures for every order that actually reached Done.
        done = self.filtered(lambda production: production.state == 'done')
        done._ddfsc_post_losses()
        done._ddfsc_sync_variance_lines()
        for production in done:
            production._ddfsc_post_variance_summary(_('Production completed'))
        return res

    def _ddfsc_sync_variance_lines(self, snapshot_plan=False):
        """Keep an auditable BoM snapshot beside the recorded consumption.

        ``stock.move.product_uom_qty`` is operational demand and can be edited
        during production. This snapshot is calculated from the BoM at
        confirmation, before operators record their actual use.
        """
        # The register is system-maintained: operators never write it directly,
        # so it is kept with sudo while the order itself stays under the user's rights.
        VarianceLine = self.env['ddfsc.production.variance.line'].sudo()
        for production in self:
            # Backorders are created already confirmed (Odoo skips action_confirm),
            # so take their snapshot the first time they are synced.
            if (snapshot_plan or production.state not in ('draft', 'cancel')) \
                    and not production.ddfsc_variance_snapshot_taken:
                production.sudo().write({
                    'ddfsc_planned_output_qty': production.product_qty,
                    'ddfsc_variance_snapshot_taken': True,
                })
            if not production.ddfsc_variance_snapshot_taken:
                continue
            planned_output = production.ddfsc_planned_output_qty or production.product_qty
            # Standard for what was really made: done orders use the produced
            # quantity, running orders the quantity being produced.
            actual_output = production.qty_produced if production.state == 'done' else production.qty_producing
            existing = {
                line.move_id.id: line for line in production.sudo().ddfsc_variance_line_ids
                if line.move_id
            }
            moves = production.move_raw_ids.filtered(
                lambda item: item.state != 'cancel' or item.id in existing
            )
            for move in moves:
                line = existing.get(move.id)
                planned = line.planned_qty if line else production._ddfsc_planned_move_qty(move)
                expected = (
                    planned * actual_output / planned_output
                    if planned_output and actual_output else planned
                )
                vals = {
                    'actual_qty': move.quantity if move.state != 'cancel' else 0.0,
                    'expected_qty': expected,
                    'is_unplanned': not bool(move.bom_line_id),
                    'unit_cost': move.product_id.uom_id._compute_price(
                        move.product_id.standard_price, move.product_uom),
                }
                if line:
                    line.write(vals)
                else:
                    VarianceLine.create({
                        'production_id': production.id,
                        'move_id': move.id,
                        'product_id': move.product_id.id,
                        'uom_id': move.product_uom.id,
                        'planned_qty': planned,
                        **vals,
                    })

    def _ddfsc_planned_move_qty(self, move):
        """Return the original BoM expectation in the move's UoM."""
        self.ensure_one()
        bom_line = move.bom_line_id
        if not bom_line or not self.bom_id or not self.bom_id.product_qty:
            return 0.0
        planned_output = self.ddfsc_planned_output_qty or self.product_qty
        output_in_bom_uom = self.product_uom_id._compute_quantity(
            planned_output, self.bom_id.product_uom_id,
        )
        factor = output_in_bom_uom / self.bom_id.product_qty
        return bom_line.product_uom_id._compute_quantity(
            bom_line.product_qty * factor, move.product_uom,
        )

    def _ddfsc_byproduct_location(self):
        """The department-specific holding location for saleable by-products."""
        self.ensure_one()
        department = self.ddfsc_department or department_for_line(self.ddfsc_line_id.code)
        xmlid = DEPARTMENTS.get(department, {}).get('byproduct_location')
        return self.env.ref(
            'ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False,
        ) if xmlid else self.env['stock.location']

    def _ddfsc_post_losses(self):
        for production in self.filtered(lambda item: item.state == 'done' and not item.ddfsc_loss_posted):
            lot = production.lot_producing_ids[:1]
            # Breakage is a measured, controlled production by-product.  It is
            # recorded under a distinct saleable product and held for store
            # acceptance.
            if production.scrap_qty:
                byproduct = production._ddfsc_saleable_byproduct()
                if byproduct:
                    production._ddfsc_post_saleable_byproduct(byproduct, production.scrap_qty)
                else:
                    production._ddfsc_post_scrap(production.scrap_qty, lot, 'Scrap')
            # Sweepings are floor waste weighed in kg.  The material they came
            # from is already in the recorded ingredient consumption, so they are
            # a reported loss (shift report, mass balance), never a deduction
            # from good finished stock.
            if production.sweeping_qty:
                production.message_post(body=_(
                    'Sweepings / waste recorded: %(qty)s kg (not saleable).', qty=production.sweeping_qty))
            production.ddfsc_loss_posted = True

    def _ddfsc_post_scrap(self, quantity, lot, label):
        self.ensure_one()
        if not quantity:
            return
        if self.product_id.tracking != 'none' and not lot:
            raise UserError(_('Set the finished lot before posting scrap or sweeping.'))
        scrap = self.env['stock.scrap'].create({
            'product_id': self.product_id.id,
            'scrap_qty': quantity,
            'product_uom_id': self.product_uom_id.id,
            'location_id': self.location_dest_id.id,
            'lot_id': lot.id if lot else False,
            'origin': '%s %s' % (label, self.name),
        })
        scrap.do_scrap()

    def _ddfsc_saleable_byproduct(self):
        self.ensure_one()
        mapping = {
            'PASTA': 'product_pasta_breakage',
            'MAC': 'product_pasta_breakage',
            'BREAD': 'product_bread_breakage',
            'BISC-CN': 'product_biscuit_breakage',
            'BISC-OR': 'product_biscuit_breakage',
        }
        xmlid = mapping.get(self.ddfsc_line_id.code)
        if not xmlid:
            return self.env['product.product']
        template = self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
        return template.product_variant_id if template else self.env['product.product']

    def _ddfsc_post_saleable_byproduct(self, product, quantity):
        """Create traceable stock of a named by-product from this MO."""
        self.ensure_one()
        location_dest = self._ddfsc_byproduct_location()
        if not location_dest:
            raise UserError(_('No saleable by-product location is configured for this department.'))
        # Odoo's virtual Production location is company-specific in this
        # database, so it may not have a portable XML id.
        production_location = self.env['stock.location'].search([
            ('usage', '=', 'production'),
            ('company_id', 'in', [self.company_id.id, False]),
        ], limit=1)
        if not production_location:
            raise UserError(_('No virtual Production location is configured for this company.'))
        move = self.env['stock.move'].create({
            'product_id': product.id,
            'product_uom_qty': quantity,
            'product_uom': product.uom_id.id,
            'location_id': production_location.id,
            'location_dest_id': location_dest.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'picked': True,
            'move_line_ids': [Command.create({
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'quantity': quantity,
                'location_id': production_location.id,
                'location_dest_id': location_dest.id,
            })],
        })
        move._action_done()

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


class DdfscProductionVarianceLine(models.Model):
    """Audit register of ingredient use per manufacturing order.

    ``planned_qty`` is frozen from the recipe when the order is confirmed.
    ``expected_qty`` is the recipe standard for the quantity actually produced,
    so producing less never hides over-use (and producing more never looks
    like waste).  Variance = actual - expected: positive is a loss (more
    material used than the standard), negative a gain.
    """
    _name = 'ddfsc.production.variance.line'
    _description = 'Production Planned vs Actual Consumption'
    _order = 'production_id desc, id'

    production_id = fields.Many2one('mrp.production', required=True, ondelete='cascade', index=True)
    move_id = fields.Many2one('stock.move', required=True, ondelete='cascade', index=True, readonly=True)
    product_id = fields.Many2one('product.product', string='Material', required=True, readonly=True)
    uom_id = fields.Many2one('uom.uom', string='Unit', required=True, readonly=True)
    planned_qty = fields.Float(string='Planned (Recipe)', readonly=True, digits='Product Unit')
    expected_qty = fields.Float(
        string='Standard for Actual Output', readonly=True, digits='Product Unit',
        help='Recipe quantity for the quantity actually produced.',
    )
    actual_qty = fields.Float(string='Actual Used', readonly=True, digits='Product Unit')
    variance_qty = fields.Float(string='Variance', compute='_compute_variance', store=True, digits='Product Unit')
    variance_percent = fields.Float(string='Variance %', compute='_compute_variance', store=True, aggregator='avg')
    unit_cost = fields.Float(string='Unit Cost', readonly=True, aggregator=False)
    variance_value = fields.Monetary(
        string='Variance Value', compute='_compute_variance', store=True,
        help='Variance quantity at the material cost. Positive means extra cost.',
    )
    currency_id = fields.Many2one(related='production_id.company_id.currency_id', store=True)
    variance_kind = fields.Selection(
        [('loss', 'Over-use (Loss)'), ('gain', 'Saving (Gain)'), ('on_standard', 'On Standard')],
        string='Result', compute='_compute_variance', store=True,
    )
    is_unplanned = fields.Boolean(string='Not in Recipe', readonly=True)
    department = fields.Selection(related='production_id.ddfsc_department', store=True, string='Department')
    line_id = fields.Many2one(related='production_id.ddfsc_line_id', store=True, string='Production Line')
    shift_id = fields.Many2one(related='production_id.ddfsc_shift_id', store=True, string='Shift')
    finished_product_id = fields.Many2one(related='production_id.product_id', store=True, string='Finished Product')
    production_state = fields.Selection(related='production_id.state', store=True, string='Order Status')
    date = fields.Datetime(related='production_id.date_start', store=True, string='Production Start')
    production_date = fields.Date(related='production_id.ddfsc_production_date', store=True, string='Production Day')
    variance_reason = fields.Text(related='production_id.ddfsc_variance_reason', string='Explanation')

    _move_unique = models.Constraint(
        'unique(move_id)',
        'Each consumption move can appear only once in the production variance register.',
    )

    @api.depends('planned_qty', 'expected_qty', 'actual_qty', 'unit_cost', 'is_unplanned', 'uom_id')
    def _compute_variance(self):
        for line in self:
            standard = line.expected_qty if line.expected_qty or line.is_unplanned else line.planned_qty
            line.variance_qty = line.actual_qty - standard
            line.variance_percent = (line.variance_qty / standard) * 100 if standard else 0.0
            line.variance_value = line.variance_qty * line.unit_cost
            rounding = line.uom_id.rounding or 0.0001
            if abs(line.variance_qty) < rounding:
                line.variance_kind = 'on_standard'
            else:
                line.variance_kind = 'loss' if line.variance_qty > 0 else 'gain'
