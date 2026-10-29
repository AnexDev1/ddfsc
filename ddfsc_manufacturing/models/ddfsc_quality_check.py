from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CHECK_TYPES = [('moisture', 'Moisture %'), ('gluten', 'Wet gluten %'), ('granulation', 'Granulation %'), ('hlw', 'Hectoliter weight kg/hl'), ('impurity', 'Impurity %'), ('germination', 'Germination %'), ('paddness', 'Paddness'), ('weight', 'Packing weight'), ('organoleptic', 'Organoleptic score'), ('conditioning', 'Conditioning'), ('magnetic', 'Magnetic separator'), ('dryer_moisture', 'Dryer moisture %'), ('cooking', 'Pasta cooking score'), ('chlorine', 'Chlorine residue'), ('wheat_receiving', 'Wheat at receiving'), ('wheat_transfer', 'Wheat at transfer'), ('wheat_warehouse', 'Wheat at warehouse'), ('other', 'Other')]

class DdfscQualityPlan(models.Model):
    _name = 'ddfsc.quality.plan'
    _description = 'Quality Control Plan'
    _order = 'sequence, id'
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    checkpoint = fields.Selection([('incoming_wheat', 'Incoming Wheat'), ('flour_release', 'Flour Release'), ('finished_goods', 'Finished Goods Release')], required=True)
    product_ids = fields.Many2many('product.product', string='Products', required=True)
    line_ids = fields.One2many('ddfsc.quality.plan.line', 'plan_id', string='Required Tests')
    demo_specification = fields.Boolean(string='Demo Specification', default=True, help='Example limits requiring factory quality-team approval before production use.')

class DdfscQualityPlanLine(models.Model):
    _name = 'ddfsc.quality.plan.line'
    _description = 'Quality Control Plan Test'
    _order = 'sequence, id'
    plan_id = fields.Many2one('ddfsc.quality.plan', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    check_type = fields.Selection(CHECK_TYPES, required=True)
    apply_min = fields.Boolean(string='Use minimum')
    standard_min = fields.Float(string='Minimum')
    apply_max = fields.Boolean(string='Use maximum')
    standard_max = fields.Float(string='Maximum')
    note = fields.Char(string='Unit / Instruction')
    limit_type = fields.Selection([
        ('min', 'Must be at least'),
        ('max', 'Must be at most'),
        ('range', 'Must be between'),
    ], string='Acceptance Rule', compute='_compute_limit_type', inverse='_inverse_limit_type', store=True)
    specification = fields.Char(string='Required Range', compute='_compute_specification')

    @api.depends('apply_min', 'apply_max')
    def _compute_limit_type(self):
        for line in self:
            if line.apply_min and line.apply_max:
                line.limit_type = 'range'
            elif line.apply_min:
                line.limit_type = 'min'
            else:
                line.limit_type = 'max'

    def _inverse_limit_type(self):
        for line in self:
            line.apply_min = line.limit_type in ('min', 'range')
            line.apply_max = line.limit_type in ('max', 'range')

    @api.depends('limit_type', 'standard_min', 'standard_max', 'note')
    def _compute_specification(self):
        for line in self:
            unit = line.note or ''
            if line.limit_type == 'range':
                value = '%g to %g' % (line.standard_min, line.standard_max)
            elif line.limit_type == 'min':
                value = 'At least %g' % line.standard_min
            else:
                value = 'At most %g' % line.standard_max
            line.specification = '%s %s' % (value, unit) if unit else value

    @api.constrains('apply_min', 'standard_min', 'apply_max', 'standard_max')
    def _check_limits(self):
        for line in self:
            if getattr(line, 'result_type', 'numeric') == 'qualitative':
                continue
            if not line.apply_min and not line.apply_max:
                raise ValidationError(_('Every required QC test must have a minimum, a maximum, or both.'))
            if line.apply_min and line.apply_max and line.standard_min > line.standard_max:
                raise ValidationError(_('The minimum cannot be greater than the maximum.'))

class DdfscQualityCheck(models.Model):
    _name = 'ddfsc.quality.check'
    _description = 'Quality Check'
    _order = 'id desc'
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', ondelete='set null')
    lot_id = fields.Many2one('stock.lot', string='Lot', required=True, ondelete='cascade')
    product_id = fields.Many2one(related='lot_id.product_id', store=True)
    plan_line_id = fields.Many2one('ddfsc.quality.plan.line', readonly=True, ondelete='restrict')
    check_type = fields.Selection(CHECK_TYPES, required=True, default='moisture')
    measured_value = fields.Float(string='Measured Result')
    is_measured = fields.Boolean(string='Test Complete', default=False)
    apply_min = fields.Boolean(string='Use minimum')
    standard_min = fields.Float(string='Minimum')
    apply_max = fields.Boolean(string='Use maximum')
    standard_max = fields.Float(string='Maximum')
    result = fields.Selection([('pending', 'Pending'), ('pass', 'Pass'), ('fail', 'Fail')], compute='_compute_result', store=True)
    note = fields.Char()
    specification = fields.Char(string='Required Range', compute='_compute_specification')

    @api.depends('apply_min', 'standard_min', 'apply_max', 'standard_max', 'note')
    def _compute_specification(self):
        for check in self:
            unit = check.note or ''
            if check.apply_min and check.apply_max:
                value = '%g to %g' % (check.standard_min, check.standard_max)
            elif check.apply_min:
                value = 'At least %g' % check.standard_min
            elif check.apply_max:
                value = 'At most %g' % check.standard_max
            else:
                value = 'No limit configured'
            check.specification = '%s %s' % (value, unit) if unit else value

    @api.onchange('measured_value')
    def _onchange_measured_value(self):
        for check in self:
            check.is_measured = True

    @api.depends('is_measured', 'measured_value', 'apply_min', 'standard_min', 'apply_max', 'standard_max')
    def _compute_result(self):
        for check in self:
            if not check.is_measured:
                check.result = 'pending'
                continue
            ok = (not check.apply_min or check.measured_value >= check.standard_min)
            ok = ok and (not check.apply_max or check.measured_value <= check.standard_max)
            check.result = 'pass' if ok else 'fail'

    @api.model_create_multi
    def create(self, vals_list):
        checks = super().create(vals_list)
        checks.lot_id._ddfsc_apply_quality_checks()
        return checks

    def write(self, vals):
        lots = self.lot_id
        res = super().write(vals)
        (lots | self.lot_id)._ddfsc_apply_quality_checks()
        return res

    def unlink(self):
        lots = self.lot_id
        res = super().unlink()
        lots._ddfsc_apply_quality_checks()
        return res
