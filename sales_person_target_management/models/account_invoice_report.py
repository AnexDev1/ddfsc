from odoo import models, fields

class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    sale_type = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit')
    ], string='Sale Type', readonly=True)

    def _select(self):
        from odoo.tools import SQL
        return SQL("%s, move.sale_type AS sale_type", super()._select())


