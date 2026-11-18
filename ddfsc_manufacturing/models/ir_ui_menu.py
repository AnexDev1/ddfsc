from odoo import models

# Top menus of each department inside Manufacturing.
DEPARTMENT_MENUS = {
    'pasta': 'ddfsc_manufacturing.menu_ddfsc_dept_pasta',
    'bread': 'ddfsc_manufacturing.menu_ddfsc_dept_bread',
    'biscuit': 'ddfsc_manufacturing.menu_ddfsc_dept_biscuit',
    'flour': 'ddfsc_manufacturing.menu_ddfsc_dept_flour',
}
# Standard Manufacturing menus showing every department's work: for managers only.
MANAGER_MENUS = (
    'mrp.menu_mrp_manufacturing',     # Operations
    'mrp.mrp_planning_menu_root',     # Planning
    'mrp.menu_mrp_bom',               # Products
    'mrp.menu_mrp_reporting',         # Reporting
    'mrp.menu_mrp_configuration',     # Configuration
)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _load_menus_blacklist(self):
        """A user with a Department sees only that department in Manufacturing.

        Users without a Department (operation manager, general manager, admins)
        keep every menu. Done here rather than with menu groups so that an
        upgrade of Odoo's Manufacturing app cannot undo it.
        """
        hidden = list(super()._load_menus_blacklist())
        department = self.env.user.sudo().ddfsc_department
        if not department:
            return hidden
        xmlids = [xmlid for key, xmlid in DEPARTMENT_MENUS.items() if key != department]
        xmlids += MANAGER_MENUS
        data = self.env['ir.model.data']
        roots = [menu_id for menu_id in (data._xmlid_to_res_id(xmlid, raise_if_not_found=False) for xmlid in xmlids)
                 if menu_id]
        if roots:
            hidden += self.sudo().with_context(active_test=False).search([('id', 'child_of', roots)]).ids
        return hidden
