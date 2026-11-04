# -*- coding: utf-8 -*-
from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    image_128 = fields.Image(
        string='Image',
        related='product_id.image_128',
        readonly=True,
    )
    image_1920 = fields.Image(
        string='Full Image',
        related='product_id.image_1920',
        readonly=True,
    )
