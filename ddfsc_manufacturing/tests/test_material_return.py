import json

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMaterialReturn(TransactionCase):
    """Returning unused material from the floor, and disposed dough, as department users."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, department=False):
            return Users.create({
                'name': login, 'login': login, 'ddfsc_department': department,
                'group_ids': [Command.set([cls.env.ref(g).id for g in ['base.group_user'] + groups])],
            })

        cls.biscuit_user = user('mr_biscuit', ['mrp.group_mrp_user'], 'biscuit')
        cls.manager = user('mr_opm', ['mrp.group_mrp_user', 'ddfsc_manufacturing.group_ddfsc_operation_manager'])
        cls.floor = cls.env.ref('ddfsc_manufacturing.loc_biscuit')
        cls.store = cls.env.ref('ddfsc_manufacturing.loc_store')
        cls.sugar = cls.env.ref('ddfsc_manufacturing.product_sugar').product_variant_id
        cls.flour = cls.env.ref('ddfsc_manufacturing.product_flour_g2').product_variant_id

    def _return(self, lines, reason='Production stopped: no FG space'):
        return self.env['ddfsc.store.request'].with_user(self.biscuit_user).with_context(
            default_request_type='material_return',
        ).create({
            'return_reason': reason,
            'line_ids': [Command.create({'product_id': product.id, 'product_uom_qty': qty})
                         for product, qty in lines],
        })

    def test_unused_sugar_goes_back_to_general_store(self):
        self.env['stock.quant']._update_available_quantity(self.sugar, self.floor, 50.0)
        floor_before = self.sugar.with_context(location=self.floor.id).qty_available
        store_before = self.sugar.with_context(location=self.store.id).qty_available
        request = self._return([(self.sugar, 20.0)])
        self.assertTrue(request.name.startswith('MRN/'))
        self.assertEqual(request.ddfsc_department, 'biscuit')
        self.assertEqual(request.line_ids.location_id, self.floor)

        request.action_submit_to_manager()
        self.assertEqual(request.location_dest_id, self.store)
        request.with_user(self.manager).action_approve_manager()
        picking = request.picking_id
        self.assertEqual(picking.picking_type_id, self.env.ref('ddfsc_manufacturing.picking_type_material_return'))
        self.assertEqual(picking.location_id, self.floor)

        picking.with_user(self.manager).button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(request.state, 'received')
        self.assertEqual(self.sugar.with_context(location=self.floor.id).qty_available, floor_before - 20.0)
        self.assertEqual(self.sugar.with_context(location=self.store.id).qty_available, store_before + 20.0)

    def test_flour_returns_to_flour_store_and_mixed_returns_are_split(self):
        flour_only = self._return([(self.flour, 2.0)])
        flour_only.action_submit_to_manager()
        self.assertEqual(flour_only.location_dest_id, self.env.ref('ddfsc_manufacturing.loc_flour'))

        mixed = self._return([(self.flour, 2.0), (self.sugar, 5.0)])
        with self.assertRaises(UserError):
            mixed.action_submit_to_manager()

    def test_reason_is_required(self):
        request = self._return([(self.sugar, 5.0)], reason=False)
        with self.assertRaises(UserError):
            request.action_submit_to_manager()

    def test_only_recipe_materials_can_be_returned(self):
        wheat = self.env.ref('ddfsc_manufacturing.product_wheat').product_variant_id
        with self.assertRaises(Exception):
            self._return([(wheat, 1.0)])

    def test_disposed_dough_is_a_loss_and_keeps_old_approvals(self):
        mo = self.env['mrp.production'].with_user(self.biscuit_user).with_context(
            ddfsc_department='biscuit',
        ).create({
            'product_id': self.env.ref('ddfsc_manufacturing.product_zebib').product_variant_id.id,
            'product_qty': 30,
            'ddfsc_line_id': self.env['mrp.workcenter'].search([('code', '=', 'BISC-CN')], limit=1).id,
            'ddfsc_shift_id': self.env.ref('ddfsc_manufacturing.shift_1').id,
        })
        self.assertNotIn('disposed', json.loads(mo._ddfsc_fingerprint()))
        mo.disposed_qty = 12.5
        self.assertEqual(json.loads(mo._ddfsc_fingerprint())['disposed'], 12.5)
        mo.sudo().ddfsc_approval_fingerprint = json.dumps(
            dict(json.loads(mo._ddfsc_fingerprint()), disposed=10.0), sort_keys=True)
        self.assertTrue(any('Disposed dough' in change for change in mo._ddfsc_fingerprint_changes()))
