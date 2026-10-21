from odoo import models, fields

class SaleReport(models.Model):
    _inherit = 'sale.report'

    sale_type = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit')
    ], string='Sale Type', readonly=True)

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['sale_type'] = "s.sale_type"
        return res

    def _group_by_sale(self):
        res = super()._group_by_sale()
        res += ", s.sale_type"
        return res
