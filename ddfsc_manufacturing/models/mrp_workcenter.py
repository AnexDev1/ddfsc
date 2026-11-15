from odoo import fields, models


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    ddfsc_flour_request_qtl = fields.Float(
        string='Daily Flour Request (qtl)',
        help='Flour this line asks the mill for on a full day.',
    )
    ddfsc_variance_tolerance = fields.Float(
        string='Consumption Tolerance %',
        default=2.0,
        help='Ingredient use within this percentage of the recipe standard is accepted. '
             'Anything outside it needs a written explanation before the shift report '
             'can be submitted for approval.',
    )
