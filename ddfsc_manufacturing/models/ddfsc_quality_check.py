from odoo import api, fields, models


class DdfscQualityCheck(models.Model):
    _name = 'ddfsc.quality.check'
    _description = 'Quality Check'
    _order = 'id desc'

    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', ondelete='set null')
    lot_id = fields.Many2one('stock.lot', string='Lot', required=True, ondelete='cascade')
    product_id = fields.Many2one(related='lot_id.product_id', store=True)
    check_type = fields.Selection(
        [
            ('moisture', 'Moisture %'),
            ('gluten', 'Wet gluten %'),
            ('granulation', 'Granulation %'),
            ('hlw', 'Hectoliter weight'),
            ('impurity', 'Impurity %'),
            ('germination', 'Germination'),
            ('paddness', 'Paddness'),
            ('weight', 'Packing weight'),
            ('organoleptic', 'Organoleptic'),
            ('conditioning', 'Conditioning'),
            ('magnetic', 'Magnetic separator'),
            ('dryer_moisture', 'Dryer moisture'),
            ('cooking', 'Pasta cooking'),
            ('chlorine', 'Chlorine residue'),
            ('wheat_receiving', 'Wheat at receiving'),
            ('wheat_transfer', 'Wheat at transfer'),
            ('wheat_warehouse', 'Wheat at warehouse'),
            ('other', 'Other'),
        ],
        required=True,
        default='moisture',
    )
    measured_value = fields.Float()
    apply_min = fields.Boolean(string='Use minimum')
    standard_min = fields.Float(string='Minimum')
    apply_max = fields.Boolean(string='Use maximum')
    standard_max = fields.Float(string='Maximum')
    result = fields.Selection(
        [('pass', 'Pass'), ('fail', 'Fail')],
        compute='_compute_result',
        store=True,
    )
    note = fields.Char()

    @api.depends('measured_value', 'apply_min', 'standard_min', 'apply_max', 'standard_max')
    def _compute_result(self):
        for check in self:
            ok = True
            if check.apply_min:
                ok = ok and check.measured_value >= check.standard_min
            if check.apply_max:
                ok = ok and check.measured_value <= check.standard_max
            check.result = 'pass' if ok else 'fail'

    @api.model_create_multi
    def create(self, vals_list):
        checks = super().create(vals_list)
        checks.lot_id._ddfsc_apply_quality_checks()
        return checks

    def write(self, vals):
        res = super().write(vals)
        self.lot_id._ddfsc_apply_quality_checks()
        return res
