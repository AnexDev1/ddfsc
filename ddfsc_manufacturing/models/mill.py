"""Mill batch figures from the extraction sheet, and flour packing bags.

The mill weighs wheat with a bin scale (counter difference × 2 = quintals),
removes screenings (impurity) at cleaning, and packs flour in 10 kg (Vera),
25 kg and 50 kg PP bags and by-product in 100 kg bags. Bags used are entered
on the order and become components issued from the Packing Materials Store.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# field on mrp.production -> (product xmlid, name)
BAGS = {
    'mill_bags_10': ('product_pp_bag_10', 'PP Bag 10 kg (Vera)'),
    'mill_bags_25': ('product_pp_bag_25', 'PP Bag 25 kg'),
    'mill_bags_50': ('product_pp_bag_50', 'PP Bag 50 kg'),
    'mill_bags_100': ('product_pp_bag_100', 'PP Bag 100 kg (By-product)'),
}
SCALE_QTL_PER_COUNT = 2.0


def mill_extraction(wheat, flour, byproduct, screenings, silo_loss_pct=0.0,
                    moisture_initial=0.0, moisture_final=0.0):
    """CER, TER and EP in %, as defined in the milling manual.

    Manual example: 100 t uncleaned wheat, 0.2 % silo loss, 2.5 t screenings,
    4 t water added, 75 t flour, 24 t bran -> CER 74.85 %.
    """
    water = 0.0
    if wheat and moisture_final and moisture_final > moisture_initial and moisture_final < 100:
        water = (wheat - screenings) * (moisture_final - moisture_initial) / (100.0 - moisture_final)
    gross_wheat = wheat * (1 + (silo_loss_pct or 0.0) / 100.0)
    conditioned = wheat - screenings + water if wheat else 0.0
    return {
        'water': water,
        'conditioned': conditioned,
        'cer': flour / gross_wheat * 100.0 if gross_wheat else 0.0,
        'ter': flour / conditioned * 100.0 if conditioned else 0.0,
        'ep': flour / (flour + byproduct) * 100.0 if flour + byproduct else 0.0,
    }


def bag_products(env):
    products = env['product.product']
    for xmlid, _name in BAGS.values():
        template = env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
        if template:
            products |= template.product_variant_id
    return products


class DdfscShift(models.Model):
    _inherit = 'ddfsc.shift'

    @api.model
    def _sync_mill_packing(self):
        for xmlid, name in BAGS.values():
            self._ensure_product(xmlid, name, 'uom.product_uom_unit')
        self._ensure_product('product_bag_thread', 'Bag Closing Thread (roll)', 'uom.product_uom_unit')


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    mill_scale_start = fields.Float(string='Bin Scale Start', copy=False,
                                    help='Bin scale counter when the batch started.')
    mill_scale_end = fields.Float(string='Bin Scale End', copy=False,
                                  help='Bin scale counter when the batch ended.')
    mill_scale_wheat_qtl = fields.Float(
        string='Wheat by Bin Scale (qtl)', compute='_compute_mill_scale', store=True,
        help='Counter difference × 2 quintals, as on the extraction sheet.')
    mill_scale_gap_qtl = fields.Float(
        string='Scale vs Recorded Wheat (qtl)', compute='_compute_mill_scale',
        help='Bin-scale wheat minus the wheat recorded as consumed. Large gaps need checking.')
    mill_impurity_kg = fields.Float(
        string='Screenings / Impurity (kg)', copy=False,
        help='Removed at cleaning before milling. Reported as a loss in the mass balance.')
    # Extraction rates as taught in the EFC milling manual (p. 215).
    mill_silo_loss_pct = fields.Float(
        string='Silo Loss %', copy=False,
        help='Loss between the silo and the working bins; the uncleaned wheat is grossed up by it for the CER.')
    mill_moisture_added_qtl = fields.Float(
        string='Water Added in Conditioning (qtl)', compute='_compute_mill_extraction',
        help='Cleaned wheat × (final − initial moisture) ÷ (100 − final moisture).')
    mill_conditioned_wheat_qtl = fields.Float(
        string='Conditioned Wheat at B1 (qtl)', compute='_compute_mill_extraction',
        help='Uncleaned wheat − screenings + water added in conditioning.')
    mill_cer = fields.Float(
        string='Commercial Extraction (CER) %', compute='_compute_mill_extraction',
        help='Total flour ÷ uncleaned wheat (grossed up by the silo loss).')
    mill_ter = fields.Float(
        string='Technical Extraction (TER) %', compute='_compute_mill_extraction',
        help='Total flour ÷ conditioned wheat at B1.')
    mill_ep = fields.Float(
        string='Extraction on Products (EP) %', compute='_compute_mill_extraction',
        help='Total flour ÷ (flour + bran and other by-products).')
    mill_bags_10 = fields.Integer(string='10 kg Bags (Vera)', copy=False)
    mill_bags_25 = fields.Integer(string='25 kg Bags', copy=False)
    mill_bags_50 = fields.Integer(string='50 kg Bags', copy=False)
    mill_bags_100 = fields.Integer(string='100 kg By-product Bags', copy=False)

    @api.depends('mill_scale_start', 'mill_scale_end', 'wheat_consumed_qtl')
    def _compute_mill_scale(self):
        for production in self:
            counted = abs((production.mill_scale_start or 0.0) - (production.mill_scale_end or 0.0))
            production.mill_scale_wheat_qtl = counted * SCALE_QTL_PER_COUNT
            production.mill_scale_gap_qtl = (
                production.mill_scale_wheat_qtl - production.wheat_consumed_qtl
                if counted and production.wheat_consumed_qtl else 0.0
            )

    @api.depends('mill_silo_loss_pct', 'mill_impurity_kg', 'moisture_initial', 'moisture_final',
                 'wheat_consumed_qtl', 'flour_produced_qtl', 'byproduct_qtl')
    def _compute_mill_extraction(self):
        for production in self:
            values = mill_extraction(
                production.wheat_consumed_qtl, production.flour_produced_qtl, production.byproduct_qtl,
                production.mill_impurity_kg / 100.0, production.mill_silo_loss_pct,
                production.moisture_initial, production.moisture_final)
            production.mill_moisture_added_qtl = values['water']
            production.mill_conditioned_wheat_qtl = values['conditioned']
            production.mill_cer = values['cer']
            production.mill_ter = values['ter']
            production.mill_ep = values['ep']

    @api.depends('mill_impurity_kg')
    def _compute_shift_figures(self):
        super()._compute_shift_figures()
        for production in self.filtered(lambda item: item.mill_impurity_kg and item.wheat_consumed_qtl):
            production.mill_unaccounted_qtl -= production.mill_impurity_kg / 100.0

    @api.constrains(*BAGS)
    def _check_mill_bags(self):
        for production in self:
            values = [production[name] for name in BAGS]
            if any(value < 0 for value in values):
                raise ValidationError(_('Bag counts cannot be negative.'))
            if any(values) and production.ddfsc_line_id.code != 'MILL':
                raise ValidationError(_('Flour packing bags are recorded on mill orders.'))

    def _ddfsc_packing_moves(self):
        self.ensure_one()
        bags = bag_products(self.env)
        return self.move_raw_ids.filtered(
            lambda move: move.product_id in bags and not move.bom_line_id and move.state != 'cancel')

    def _ddfsc_sync_bag_moves(self):
        for production in self.filtered(lambda item: item.state in ('confirmed', 'progress', 'to_close')
                                        and item.ddfsc_line_id.code == 'MILL'):
            moves = production._ddfsc_packing_moves()
            for field_name, (xmlid, _name) in BAGS.items():
                template = self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
                if not template:
                    continue
                product = template.product_variant_id
                quantity = production[field_name]
                existing = moves.filtered(lambda move: move.product_id == product)
                if quantity and not existing:
                    self.env['stock.move'].create(
                        production._get_move_raw_values(product, quantity, product.uom_id))._action_confirm()
                elif quantity:
                    existing[:1].product_uom_qty = quantity
                    (existing - existing[:1])._action_cancel()
                elif existing:
                    existing._action_cancel()
        self._ddfsc_sync_variance_lines()

    def write(self, vals):
        result = super().write(vals)
        if set(BAGS).intersection(vals):
            self._ddfsc_sync_bag_moves()
        return result

    def action_confirm(self):
        result = super().action_confirm()
        self.filtered(lambda item: any(item[name] for name in BAGS))._ddfsc_sync_bag_moves()
        return result

    @api.depends('bom_id', 'bom_id.bom_line_ids.product_id', 'ddfsc_line_id')
    def _compute_allowed_components(self):
        super()._compute_allowed_components()
        for production in self.filtered(lambda item: item.ddfsc_line_id.code == 'MILL'):
            production.allowed_component_ids |= bag_products(self.env)


class StoreRequest(models.Model):
    _inherit = 'ddfsc.store.request'

    @api.depends('ddfsc_department', 'request_type', 'production_id', 'production_id.bom_id',
                 'production_id.product_id', 'production_id.move_raw_ids')
    def _compute_allowed_products(self):
        super()._compute_allowed_products()
        for request in self:
            if request.ddfsc_department == 'flour' and request.request_type in ('component', 'material_return'):
                request.allowed_product_ids |= bag_products(self.env)
