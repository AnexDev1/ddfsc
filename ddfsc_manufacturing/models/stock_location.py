from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    ddfsc_silo_use = fields.Selection(
        [
            ('pasta', 'Pasta'),
            ('macaroni', 'Macaroni'),
            ('bread', 'Bread'),
            ('biscuit', 'Biscuit'),
        ],
        string='Wheat Kept For',
    )
    ddfsc_flour_hold = fields.Boolean(
        string='Flour Needs a Pass Before It Leaves',
    )
