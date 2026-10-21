from odoo import fields, models

from .ddfsc_department import selection


class ResUsers(models.Model):
    _inherit = 'res.users'

    ddfsc_department = fields.Selection(
        selection=selection,
        string='Department',
        help='Pasta, bread, biscuit, or flour. Store requisitions and new manufacturing orders use this department.',
    )
