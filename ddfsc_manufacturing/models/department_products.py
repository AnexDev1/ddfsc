from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

OUTPUTS = {
    'flour': ['product_flour_g1', 'product_flour_g2', 'product_flour_lcp', 'product_flour_scp'],
    'pasta': ['product_pasta_long', 'product_pasta_short'],
    'bread': ['product_bread_market', 'product_bread_university'],
    'biscuit': ['product_zebib', 'product_defense'],
}
LINES = {'MILL': 'flour', 'PASTA': 'pasta', 'MAC': 'pasta', 'BREAD': 'bread', 'BISC-CN': 'biscuit', 'BISC-OR': 'biscuit'}

def outputs(env, department, code=None):
    names = OUTPUTS.get(department, [])
    if code == 'PASTA': names = ['product_pasta_long']
    if code == 'MAC': names = ['product_pasta_short']
    products = env['product.product']
    for name in names:
        template = env.ref('ddfsc_manufacturing.' + name, raise_if_not_found=False)
        if template: products |= template.product_variant_ids
    return products

def recipes(env, products):
    return env['mrp.bom'].search([
        ('active', '=', True), ('type', '=', 'normal'),
        ('product_tmpl_id', 'in', products.product_tmpl_id.ids),
        '|', ('company_id', '=', False), ('company_id', '=', env.company.id),
    ])

class StoreRequest(models.Model):
    _inherit = 'ddfsc.store.request'

    allowed_product_ids = fields.Many2many('product.product', compute='_compute_allowed_products')
    production_id = fields.Many2one('mrp.production', string='Production Order', copy=False, index=True)

    @api.model
    def _sync_department_stock_filters(self):
        for department in OUTPUTS:
            products = outputs(self.env, department)
            for suffix in ['flour', 'temp']:
                if department == 'flour' and suffix == 'flour':
                    continue
                action = self.env.ref('ddfsc_manufacturing.action_ddfsc_%s_%s' % (department, suffix))
                allowed = products if suffix == 'temp' else recipes(self.env, products).bom_line_ids.product_id.filtered('ddfsc_is_flour')
                domain = safe_eval(action.domain)
                domain = [term for term in domain if not (isinstance(term, (tuple, list)) and term[0] == 'product_id' and term[1] == 'in')]
                domain.append(('product_id', 'in', allowed.ids))
                # Available flour is held centrally before the departmental request.
                if suffix == 'flour':
                    domain = [term for term in domain if not (isinstance(term, (tuple, list)) and term[0] == 'location_id')]
                    domain.append(('location_id', 'in', [self.env.ref('ddfsc_manufacturing.loc_flour').id]))
                action.domain = repr(domain)

    @api.depends('ddfsc_department', 'request_type', 'production_id', 'production_id.bom_id', 'production_id.product_id')
    def _compute_allowed_products(self):
        for request in self:
            products = outputs(self.env, request.ddfsc_department)
            boms = recipes(self.env, products)
            if request.production_id:
                products = request.production_id.product_id
                boms = request.production_id.bom_id
            if request.request_type == 'component':
                products = boms.bom_line_ids.product_id
            elif request.request_type == 'byproduct_return':
                products = boms.byproduct_ids.product_id if request.ddfsc_department == 'flour' else self.env['product.product']
            request.allowed_product_ids = products

    def _check_department_products(self):
        for request in self:
            invalid = request.line_ids.product_id - request.allowed_product_ids
            if invalid:
                raise ValidationError(_('These products do not belong to this department/request type: %s', ', '.join(invalid.mapped('display_name'))))

    @api.constrains('ddfsc_department', 'request_type', 'line_ids', 'production_id')
    def _constrain_department_products(self):
        self._check_department_products()

    def action_submit_to_manager(self):
        self._check_department_products()
        return super().action_submit_to_manager()

    def action_approve_manager(self):
        self._check_department_products()
        return super().action_approve_manager()

class StoreRequestLine(models.Model):
    _inherit = 'ddfsc.store.request.line'

    @api.constrains('product_id', 'request_id')
    def _constrain_department_product(self):
        self.request_id._check_department_products()

class Production(models.Model):
    _inherit = 'mrp.production'

    allowed_output_ids = fields.Many2many('product.product', compute='_compute_allowed_outputs')
    allowed_component_ids = fields.Many2many('product.product', compute='_compute_allowed_components')
    department_line_ids = fields.Many2many('mrp.workcenter', compute='_compute_department_lines')

    @api.depends_context('ddfsc_department')
    @api.depends('ddfsc_line_id')
    def _compute_department_lines(self):
        for production in self:
            department = self.env.context.get('ddfsc_department') or LINES.get(production.ddfsc_line_id.code) or self.env.user.ddfsc_department
            codes = [code for code, dep in LINES.items() if not department or dep == department]
            production.department_line_ids = self.env['mrp.workcenter'].search([('code', 'in', codes)])

    def _action_department_request(self, kind):
        self.ensure_one()
        department = LINES.get(self.ddfsc_line_id.code)
        if not department or not self.bom_id:
            raise ValidationError(_('Choose the production line, finished product and recipe first.'))
        existing = self.env['ddfsc.store.request'].search([('production_id', '=', self.id), ('request_type', '=', kind), ('state', '!=', 'cancel')])
        action = self.env.ref('ddfsc_manufacturing.action_ddfsc_store_requests').read()[0]
        action['context'] = {'default_ddfsc_department': department, 'default_request_type': kind, 'default_production_id': self.id}
        if existing:
            action.update(domain=[('id', 'in', existing.ids)])
            if len(existing) == 1:
                action.update(view_mode='form', views=[(False, 'form')], res_id=existing.id)
            return action
        lines = []
        if kind == 'component':
            if self.state in ('done', 'cancel'):
                raise ValidationError(_('Request ingredients before completing production.'))
            # Use the order's exploded components, including their actual units.
            for move in self.move_raw_ids.filtered(lambda m: m.state != 'cancel'):
                lines.append(fields.Command.create({'product_id': move.product_id.id, 'product_uom_qty': move.product_uom_qty, 'product_uom_id': move.product_uom.id}))
        else:
            if self.state != 'done':
                raise ValidationError(_('Complete production before requesting a finished goods transfer.'))
            lines.append(fields.Command.create({'product_id': self.product_id.id, 'product_uom_qty': self.qty_produced, 'product_uom_id': self.product_uom_id.id}))
        if not lines:
            raise ValidationError(_('The recipe has no ingredients to request.'))
        action['context']['default_line_ids'] = lines
        action.update(view_mode='form', views=[(False, 'form')])
        return action

    def action_request_ingredients(self):
        return self._action_department_request('component')

    def action_request_finished_goods(self):
        return self._action_department_request('finished_goods')

    @api.depends('bom_id', 'bom_id.bom_line_ids.product_id')
    def _compute_allowed_components(self):
        for production in self:
            production.allowed_component_ids = production.bom_id.bom_line_ids.product_id

    @api.depends('ddfsc_line_id')
    @api.depends_context('ddfsc_department')
    def _compute_allowed_outputs(self):
        for production in self:
            code = production.ddfsc_line_id.code
            department = LINES.get(code) or self.env.context.get('ddfsc_department') or self.env.user.ddfsc_department
            production.allowed_output_ids = outputs(self.env, department, code) if department else self.env['product.product'].union(*(outputs(self.env, key) for key in OUTPUTS))

    @api.constrains('product_id', 'ddfsc_line_id', 'bom_id')
    def _check_department_output(self):
        for production in self:
            if production.ddfsc_line_id or self.env.context.get('ddfsc_department'):
                if production.product_id.id not in production.allowed_output_ids.ids:
                    raise ValidationError(_('Select a product belonging to the chosen production line/department.'))
                if production.bom_id and (production.bom_id.product_tmpl_id != production.product_id.product_tmpl_id or (production.bom_id.product_id and production.bom_id.product_id != production.product_id)):
                    raise ValidationError(_('The recipe must belong to the selected product.'))

    def action_confirm(self):
        self._check_department_output()
        for production in self:
            if production.ddfsc_line_id:
                allowed = production.bom_id.bom_line_ids.product_id
                invalid = production.move_raw_ids.product_id - allowed
                if invalid:
                    raise ValidationError(_('Components must belong to the selected recipe: %s', ', '.join(invalid.mapped('display_name'))))
        return super().action_confirm()
