from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    ddfsc_is_flour = fields.Boolean(string='Counts as Flour')
    ddfsc_is_byproduct = fields.Boolean(string='Saleable By-product')
    ddfsc_qc_required = fields.Boolean(
        string='QC Release Required', default=True,
        help='Untick for products released without a QC inspection (bread): their lots get no '
             'inspection and go to finished goods directly.')
    ddfsc_byproduct_department = fields.Selection(
        [
            ('flour', 'Flour'),
            ('pasta', 'Pasta / Macaroni'),
            ('bread', 'Bread'),
            ('biscuit', 'Biscuit'),
        ],
        string='By-product Department',
        help='Department that produces this saleable by-product.',
    )
