from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLossCorrection(TransactionCase):
    """Late sweepings on a closed order: Operation Manager only, before QC or FG transfer."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, department=False):
            return Users.create({
                'name': login, 'login': login, 'ddfsc_department': department,
                'group_ids': [Command.set([cls.env.ref(g).id for g in ['base.group_user'] + groups])],
            })

        cls.pasta_user = user('lc_pasta', ['mrp.group_mrp_user'], 'pasta')
        cls.manager = user('lc_opm', ['mrp.group_mrp_user', 'ddfsc_manufacturing.group_ddfsc_operation_manager'])

    def _done_order(self):
        product = self.env.ref('ddfsc_manufacturing.product_pasta_long').product_variant_id
        mo = self.env['mrp.production'].with_user(self.pasta_user).with_context(ddfsc_department='pasta').create({
            'product_id': product.id, 'product_qty': 100,
            'ddfsc_line_id': self.env['mrp.workcenter'].search([('code', '=', 'PASTA')], limit=1).id,
            'ddfsc_shift_id': self.env.ref('ddfsc_manufacturing.shift_1').id,
            'date_start': fields.Datetime.now(),
        })
        mo.action_confirm()
        for move in mo.move_raw_ids:
            lot = self.env['stock.lot'].create({'name': 'LC-%s' % move.id, 'product_id': move.product_id.id}) \
                if move.product_id.tracking == 'lot' else None
            self.env['stock.quant']._update_available_quantity(
                move.product_id, mo.location_src_id, move.product_uom_qty * 2, lot_id=lot)
        mo.action_assign()
        mo.qty_producing = 100
        mo.set_qty_producing()
        mo.move_raw_ids.picked = True
        if not mo.lot_producing_ids:
            mo.action_generate_serial()
        mo.write({'sweeping_qty': 4.0})
        mo.action_ddfsc_submit()
        mo.with_user(self.manager).action_ddfsc_approve()
        result = mo.button_mark_done()
        if isinstance(result, dict) and result.get('res_model') == 'mrp.consumption.warning':
            self.env['mrp.consumption.warning'].with_context(**result['context']).create({}).action_confirm()
        self.assertEqual(mo.state, 'done')
        return mo

    def _correct(self, mo, user, **values):
        mo.with_user(user).action_ddfsc_correct_losses()
        wizard = self.env['ddfsc.loss.correction.wizard'].with_user(user).with_context(
            default_production_id=mo.id).create(values)
        return wizard.action_apply()

    def test_manager_corrects_sweepings_with_a_reason(self):
        mo = self._done_order()
        self.assertTrue(mo.with_user(self.manager).ddfsc_can_correct_losses)
        self._correct(mo, self.manager, sweeping_qty=6.5, reason='Weighed after cleaning the floor')
        self.assertEqual(mo.sweeping_qty, 6.5)
        self.assertIn('4.0 → 6.5', mo.message_ids[0].body)

    def test_operator_cannot_correct_and_reason_is_required(self):
        mo = self._done_order()
        with self.assertRaises(UserError):
            mo.with_user(self.pasta_user).action_ddfsc_correct_losses()
        wizard = self.env['ddfsc.loss.correction.wizard'].with_user(self.manager).with_context(
            default_production_id=mo.id).create({'sweeping_qty': 5.0, 'reason': ' '})
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_locked_once_qc_decided_or_sent_to_finished_goods(self):
        mo = self._done_order()
        mo.lot_producing_ids.write({'ddfsc_quality_state': 'pass'})
        self.assertFalse(mo.ddfsc_can_correct_losses)
        with self.assertRaises(UserError):
            mo.with_user(self.manager).action_ddfsc_correct_losses()
