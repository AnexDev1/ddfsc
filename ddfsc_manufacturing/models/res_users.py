from odoo import fields, models

from .ddfsc_department import selection


class ResUsers(models.Model):
    _inherit = 'res.users'

    ddfsc_department = fields.Selection(
        selection=selection,
        string='Department',
        help='Pasta, bread, biscuit, or flour. Store requisitions and new manufacturing orders use this '
             'department, and the user sees only that department in Manufacturing. Leave empty for '
             'managers who see every department.',
    )

    def write(self, vals):
        result = super().write(vals)
        if 'ddfsc_department' in vals:
            # The menus a user sees are cached; the department decides them.
            self.env.registry.clear_cache()
        return result
