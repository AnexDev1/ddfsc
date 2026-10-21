# -*- coding: utf-8 -*-
from odoo import models, fields

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    product_code = fields.Char(related='product_id.default_code', string='Product Code', store=False, related_sudo=True)
    product_name_only = fields.Char(related='product_id.name', string='Product Name', store=False, related_sudo=True)
