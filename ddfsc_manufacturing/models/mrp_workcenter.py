from odoo import fields, models


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    ddfsc_flour_request_qtl = fields.Float(
        string='Daily Flour Request (qtl)',
        help='Flour this line asks the mill for on a full day.',
    )
