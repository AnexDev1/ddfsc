"""Rework: breakage taken back from the store and reused in production.

The factory grinds biscuit scrap back into the dough and re-uses pasta rework
powder. The scrap first goes to the store as a saleable by-product; a line
that reworks it requests it back like any ingredient, so every kilogram is
issued, consumed and costed through normal stock moves.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .department_products import byproducts

REWORK_LINES = ('PASTA', 'MAC', 'BISC-CN', 'BISC-OR')
REWORK_DEPARTMENTS = ('pasta', 'biscuit')


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    ddfsc_rework_qty = fields.Float(
        string='Reworked Scrap Used (kg)',
        copy=False,
        tracking=True,
        help='Ground biscuit scrap or pasta rework powder put back into this production. '
             'It is added as a component, requested from the store with the other ingredients, '
             'and consumed from the production floor.',
    )
    ddfsc_can_rework = fields.Boolean(compute='_compute_ddfsc_can_rework')

    @api.depends('ddfsc_line_id')
    def _compute_ddfsc_can_rework(self):
        for production in self:
            production.ddfsc_can_rework = bool(production._ddfsc_rework_product())

    def _ddfsc_rework_product(self):
        self.ensure_one()
        if self.ddfsc_line_id.code not in REWORK_LINES:
            return self.env['product.product']
        return self._ddfsc_saleable_byproduct()

    def _ddfsc_rework_moves(self):
        self.ensure_one()
        product = self._ddfsc_rework_product()
        return self.move_raw_ids.filtered(
            lambda move: product and move.product_id == product and not move.bom_line_id
            and move.state != 'cancel'
        )

    @api.constrains('ddfsc_rework_qty', 'ddfsc_line_id')
    def _check_ddfsc_rework_qty(self):
        for production in self:
            if production.ddfsc_rework_qty < 0:
                raise ValidationError(_('Reworked scrap cannot be negative.'))
            if production.ddfsc_rework_qty and not production._ddfsc_rework_product():
                raise ValidationError(_('Only the pasta and biscuit lines rework scrap.'))

    def _ddfsc_sync_rework_move(self):
        for production in self.filtered(lambda item: item.state in ('confirmed', 'progress', 'to_close')):
            product = production._ddfsc_rework_product()
            if not product:
                continue
            moves = production._ddfsc_rework_moves()
            quantity = production.ddfsc_rework_qty
            if quantity and not moves:
                values = production._get_move_raw_values(product, quantity, product.uom_id)
                self.env['stock.move'].create(values)._action_confirm()
            elif quantity:
                moves[:1].product_uom_qty = quantity
                (moves - moves[:1])._action_cancel()
            elif moves:
                moves._action_cancel()
        self._ddfsc_sync_variance_lines()

    def write(self, vals):
        result = super().write(vals)
        if 'ddfsc_rework_qty' in vals:
            self._ddfsc_sync_rework_move()
        return result

    def action_confirm(self):
        result = super().action_confirm()
        self.filtered('ddfsc_rework_qty')._ddfsc_sync_rework_move()
        return result

    @api.depends('bom_id', 'bom_id.bom_line_ids.product_id', 'ddfsc_line_id')
    def _compute_allowed_components(self):
        super()._compute_allowed_components()
        for production in self:
            production.allowed_component_ids |= production._ddfsc_rework_product()


class StoreRequest(models.Model):
    _inherit = 'ddfsc.store.request'

    @api.depends('ddfsc_department', 'request_type', 'production_id', 'production_id.bom_id',
                 'production_id.product_id', 'production_id.move_raw_ids')
    def _compute_allowed_products(self):
        super()._compute_allowed_products()
        for request in self:
            if request.request_type not in ('component', 'material_return'):
                continue
            if request.production_id:
                request.allowed_product_ids |= request.production_id._ddfsc_rework_moves().product_id
            elif request.ddfsc_department in REWORK_DEPARTMENTS:
                request.allowed_product_ids |= byproducts(self.env, request.ddfsc_department)
