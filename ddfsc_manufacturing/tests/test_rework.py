from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRework(TransactionCase):
    """Scrap reused in production, requested back from the store (department users only)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, department=False):
            return Users.create({
                'name': login, 'login': login, 'ddfsc_department': department,
                'group_ids': [Command.set([cls.env.ref(g).id for g in ['base.group_user'] + groups])],
            })

        cls.biscuit_user = user('rw_biscuit', ['mrp.group_mrp_user'], 'biscuit')
        cls.bread_user = user('rw_bread', ['mrp.group_mrp_user'], 'bread')
        cls.scrap = cls.env.ref('ddfsc_manufacturing.product_biscuit_breakage').product_variant_id
        cls.store = cls.env.ref('ddfsc_manufacturing.loc_store')

    def _mo(self, user, code, xmlid, qty):
        return self.env['mrp.production'].with_user(user).with_context(
            ddfsc_department=user.ddfsc_department,
        ).create({
            'product_id': self.env.ref('ddfsc_manufacturing.%s' % xmlid).product_variant_id.id,
            'product_qty': qty,
            'ddfsc_line_id': self.env['mrp.workcenter'].search([('code', '=', code)], limit=1).id,
            'ddfsc_shift_id': self.env.ref('ddfsc_manufacturing.shift_1').id,
            'date_start': fields.Datetime.now(),
        })

    def test_rework_is_a_component_requested_from_the_store(self):
        mo = self._mo(self.biscuit_user, 'BISC-CN', 'product_zebib', 30)
        mo.action_confirm()
        mo.ddfsc_rework_qty = 15.0
        rework = mo._ddfsc_rework_moves()
        self.assertEqual(rework.product_id, self.scrap)
        self.assertEqual(rework.product_uom_qty, 15.0)
        self.assertEqual(rework.location_id, mo.location_src_id)

        action = mo.action_request_ingredients()
        request = self.env['ddfsc.store.request'].with_user(self.biscuit_user).with_context(
            **action['context']).create({})
        scrap_line = request.line_ids.filtered(lambda line: line.product_id == self.scrap)
        self.assertEqual(scrap_line.product_uom_qty, 15.0)
        self.assertEqual(scrap_line.location_id, self.store)

        variance = mo.sudo().ddfsc_variance_line_ids.filtered(lambda line: line.move_id == rework)
        self.assertTrue(variance.is_rework)
        self.assertNotIn(variance, mo._ddfsc_variances_over_tolerance())

        mo.ddfsc_rework_qty = 20.0
        self.assertEqual(mo._ddfsc_rework_moves().product_uom_qty, 20.0)
        mo.ddfsc_rework_qty = 0.0
        self.assertFalse(mo._ddfsc_rework_moves())

    def test_rework_entered_before_confirmation(self):
        mo = self._mo(self.biscuit_user, 'BISC-CN', 'product_zebib', 30)
        mo.ddfsc_rework_qty = 6.0
        mo.action_confirm()
        self.assertEqual(mo._ddfsc_rework_moves().product_uom_qty, 6.0)

    def test_department_store_request_can_ask_for_scrap(self):
        request = self.env['ddfsc.store.request'].with_user(self.biscuit_user).with_context(
            default_request_type='component',
        ).create({'line_ids': [Command.create({'product_id': self.scrap.id, 'product_uom_qty': 10.0})]})
        self.assertIn(self.scrap, request.allowed_product_ids)

    def test_bread_does_not_rework(self):
        mo = self._mo(self.bread_user, 'BREAD', 'product_bread_market', 1400)
        self.assertFalse(mo.ddfsc_can_rework)
        with self.assertRaises(ValidationError):
            mo.ddfsc_rework_qty = 5.0
