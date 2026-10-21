from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    ddfsc_is_flour = fields.Boolean(string='Counts as Flour')
    ddfsc_is_byproduct = fields.Boolean(string='Mill By-product')
