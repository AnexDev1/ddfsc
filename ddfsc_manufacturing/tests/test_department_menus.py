from odoo import Command
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDepartmentMenus(TransactionCase):
    """A user with a Department sees only that department in Manufacturing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = ['base.group_user', 'mrp.group_mrp_manager', 'stock.group_stock_user']
        cls.user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Flour Admin', 'login': 'dm_flour', 'ddfsc_department': 'flour',
            'group_ids': [Command.set([cls.env.ref(g).id for g in groups])],
        })
        cls.root = cls.env.ref('mrp.menu_mrp_root')

    def _manufacturing_menus(self, user):
        menus = self.env['ir.ui.menu'].with_user(user).load_menus(False)
        return set(menus[self.root.id]['children'])

    def _id(self, xmlid):
        return self.env.ref(xmlid).id

    def test_department_user_sees_only_their_department(self):
        visible = self._manufacturing_menus(self.user)
        self.assertEqual(visible, {self._id('ddfsc_manufacturing.menu_ddfsc_dept_flour')})
        flour_entries = self.env['ir.ui.menu'].with_user(self.user).load_menus(False)[
            self._id('ddfsc_manufacturing.menu_ddfsc_dept_flour')]['children']
        self.assertTrue(flour_entries, 'The Flour menu keeps its entries')

    def test_changing_the_department_changes_the_menus(self):
        self._manufacturing_menus(self.user)  # fill the cache
        self.user.ddfsc_department = 'pasta'
        self.assertEqual(self._manufacturing_menus(self.user),
                         {self._id('ddfsc_manufacturing.menu_ddfsc_dept_pasta')})

    def test_user_without_department_sees_everything(self):
        self.user.ddfsc_department = False
        visible = self._manufacturing_menus(self.user)
        for xmlid in ('ddfsc_manufacturing.menu_ddfsc_dept_pasta', 'ddfsc_manufacturing.menu_ddfsc_dept_bread',
                      'ddfsc_manufacturing.menu_ddfsc_dept_biscuit', 'ddfsc_manufacturing.menu_ddfsc_dept_flour',
                      'mrp.menu_mrp_manufacturing', 'mrp.menu_mrp_configuration'):
            self.assertIn(self._id(xmlid), visible, xmlid)
