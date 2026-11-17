from odoo import Command, fields
from odoo.exceptions import RedirectWarning
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestQcScope(TransactionCase):
    """Bread goes to FG without QC; departments receive flour from the Flour Store without QC."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, department=False):
            return Users.create({
                'name': login, 'login': login, 'ddfsc_department': department,
                'group_ids': [Command.set([cls.env.ref(g).id for g in ['base.group_user'] + groups])],
            })

        cls.bread_user = user('qs_bread', ['mrp.group_mrp_user'], 'bread')
        cls.biscuit_user = user('qs_biscuit', ['mrp.group_mrp_user'], 'biscuit')
        cls.manager = user('qs_opm', ['mrp.group_mrp_user', 'ddfsc_manufacturing.group_ddfsc_operation_manager'])
        cls.store = user('qs_store', ['stock.group_stock_manager'])
        cls.bread = cls.env.ref('ddfsc_manufacturing.product_bread_market')
        cls.bread.ddfsc_qc_required = False  # as set by the upgrade
        cls.flour = cls.env.ref('ddfsc_manufacturing.product_flour_g2').product_variant_id

    def _done_bread_order(self):
        mo = self.env['mrp.production'].with_user(self.bread_user).with_context(ddfsc_department='bread').create({
            'product_id': self.bread.product_variant_id.id, 'product_qty': 1400,
            'ddfsc_line_id': self.env['mrp.workcenter'].search([('code', '=', 'BREAD')], limit=1).id,
            'ddfsc_shift_id': self.env.ref('ddfsc_manufacturing.shift_1').id,
            'date_start': fields.Datetime.now(),
        })
        mo.action_confirm()
        for move in mo.move_raw_ids:
            lot = self.env['stock.lot'].create({'name': 'QS-%s' % move.id, 'product_id': move.product_id.id}) \
                if move.product_id.tracking == 'lot' else None
            self.env['stock.quant']._update_available_quantity(
                move.product_id, mo.location_src_id, move.product_uom_qty * 2, lot_id=lot)
        mo.action_assign()
        mo.qty_producing = 1400
        mo.set_qty_producing()
        mo.move_raw_ids.picked = True
        if mo.product_id.tracking == 'lot' and not mo.lot_producing_ids:
            mo.action_generate_serial()
        mo.action_ddfsc_submit()
        mo.with_user(self.manager).action_ddfsc_approve()
        result = mo.button_mark_done()
        if isinstance(result, dict) and result.get('res_model') == 'mrp.consumption.warning':
            self.env['mrp.consumption.warning'].with_context(**result['context']).create({}).action_confirm()
        self.assertEqual(mo.state, 'done')
        return mo

    def test_bread_goes_to_finished_goods_without_qc(self):
        mo = self._done_bread_order()
        self.assertFalse(mo.lot_producing_ids.quality_plan_id, 'Bread lots get no QC plan')
        action = mo.with_user(self.bread_user).action_request_finished_goods()
        request = self.env['ddfsc.store.request'].with_user(self.bread_user).with_context(
            **action['context']).create({})
        request.action_submit_to_manager()
        request.with_user(self.manager).action_approve_manager()
        request.picking_id.with_user(self.store).button_validate()
        self.assertEqual(request.picking_id.state, 'done')

    def test_department_receives_flour_from_the_store_without_qc(self):
        flour_store = self.env.ref('ddfsc_manufacturing.loc_flour')
        lot = self.env['stock.lot'].create({'name': 'QS-FLOUR-PENDING', 'product_id': self.flour.id})
        self.assertEqual(lot.ddfsc_quality_state, 'pending')
        self.env['stock.quant']._update_available_quantity(self.flour, flour_store, 10.0, lot_id=lot)
        request = self.env['ddfsc.store.request'].with_user(self.biscuit_user).with_context(
            default_request_type='component',
        ).create({'line_ids': [Command.create({'product_id': self.flour.id, 'product_uom_qty': 3.0,
                                               'lot_id': lot.id})]})
        request.action_submit_to_manager()
        request.with_user(self.manager).action_approve_manager()
        request.picking_id.with_user(self.store).button_validate()
        self.assertEqual(request.picking_id.state, 'done')
        self.assertEqual(request.state, 'received')

    def test_flour_is_still_checked_before_the_flour_store(self):
        temp = self.env.ref('ddfsc_manufacturing.loc_flour_finished')
        flour_store = self.env.ref('ddfsc_manufacturing.loc_flour')
        lot = self.env['stock.lot'].create({'name': 'QS-FLOUR-TEMP', 'product_id': self.flour.id})
        self.env['stock.quant']._update_available_quantity(self.flour, temp, 5.0, lot_id=lot)
        picking_type = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1).int_type_id
        picking = self.env['stock.picking'].with_user(self.store).create({
            'picking_type_id': picking_type.id, 'location_id': temp.id, 'location_dest_id': flour_store.id,
            'move_ids': [Command.create({'product_id': self.flour.id, 'product_uom_qty': 5.0,
                                         'location_id': temp.id, 'location_dest_id': flour_store.id})],
        })
        picking.action_confirm()
        picking.action_assign()
        with self.assertRaises(RedirectWarning):
            picking.button_validate()
