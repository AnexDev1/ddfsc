from datetime import datetime, timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDepartmentFlows(TransactionCase):
    """Regression tests run as real department users, never as admin."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, department=False):
            return Users.create({
                'name': login, 'login': login, 'ddfsc_department': department,
                'group_ids': [Command.set([cls.env.ref(g).id for g in ['base.group_user'] + groups])],
            })

        cls.pasta_user = user('t_pasta', ['mrp.group_mrp_user'], 'pasta')
        cls.biscuit_user = user('t_biscuit', ['mrp.group_mrp_user'], 'biscuit')
        cls.manager = user('t_opm', ['mrp.group_mrp_user', 'ddfsc_manufacturing.group_ddfsc_operation_manager'])
        cls.shift = cls.env.ref('ddfsc_manufacturing.shift_1')

    def _product(self, xmlid):
        return self.env.ref('ddfsc_manufacturing.%s' % xmlid).product_variant_id

    def _line(self, code):
        return self.env['mrp.workcenter'].search([('code', '=', code)], limit=1)

    def _mo(self, user, code, product, qty, shift=None, date=None):
        return self.env['mrp.production'].with_user(user).with_context(
            ddfsc_department=user.ddfsc_department,
        ).create({
            'product_id': self._product(product).id, 'product_qty': qty,
            'ddfsc_line_id': self._line(code).id, 'ddfsc_shift_id': (shift or self.shift).id,
            'date_start': date or fields.Datetime.now(),
        })

    def _stock_floor(self, mo):
        for move in mo.move_raw_ids:
            lot = None
            if move.product_id.tracking == 'lot':
                lot = self.env['stock.lot'].create({'name': 'T-%s' % move.id, 'product_id': move.product_id.id})
            self.env['stock.quant']._update_available_quantity(
                move.product_id, mo.location_src_id, move.product_uom_qty * 2, lot_id=lot)

    def _produce(self, mo, user, qty):
        mo = mo.with_user(user)
        mo.action_assign()
        mo.qty_producing = qty
        mo.set_qty_producing()
        mo.move_raw_ids.picked = True
        if mo.product_id.tracking == 'lot' and not mo.lot_producing_ids:
            mo.action_generate_serial()
        return mo

    def test_department_user_confirms_and_variance_is_recorded(self):
        """Department users could not confirm: the variance register was read-only for them."""
        mo = self._mo(self.pasta_user, 'PASTA', 'product_pasta_long', 400)
        mo.action_confirm()
        self.assertEqual(mo.state, 'confirmed')
        self.assertTrue(mo.sudo().ddfsc_variance_line_ids)

    def test_macaroni_and_orland_belong_to_their_departments(self):
        mac = self._mo(self.pasta_user, 'MAC', 'product_pasta_short', 100)
        orland = self._mo(self.biscuit_user, 'BISC-OR', 'product_defense', 10)
        self.assertEqual(mac.ddfsc_department, 'pasta')
        self.assertEqual(orland.ddfsc_department, 'biscuit')
        self.assertIn(mac, self.env['mrp.production'].with_user(self.pasta_user).search([]))
        self.assertEqual(mac._ddfsc_byproduct_location(),
                         self.env.ref('ddfsc_manufacturing.loc_pasta_byproduct'))

    def test_overuse_needs_explanation_and_standard_follows_actual_output(self):
        mo = self._mo(self.pasta_user, 'PASTA', 'product_pasta_long', 400)
        mo.action_confirm()
        self._stock_floor(mo)
        mo = self._produce(mo, self.pasta_user, 300)
        flour = mo.move_raw_ids[:1]
        flour.move_line_ids[1:].unlink()
        flour.move_line_ids.quantity = 1.60          # standard for 300 packs is 1.50 qtl
        with self.assertRaises(UserError):
            mo.action_ddfsc_submit()
        mo.ddfsc_variance_reason = 'Die change'
        mo.action_ddfsc_submit()
        line = mo.sudo().ddfsc_variance_line_ids.filtered(lambda item: item.move_id == flour)
        self.assertAlmostEqual(line.planned_qty, 2.0)
        self.assertAlmostEqual(line.expected_qty, 1.5)
        self.assertAlmostEqual(line.variance_qty, 0.1)
        self.assertEqual(line.variance_kind, 'loss')

    def test_changes_after_approval_withdraw_the_approval(self):
        mo = self._mo(self.pasta_user, 'PASTA', 'product_pasta_long', 200)
        mo.action_confirm()
        self._stock_floor(mo)
        mo = self._produce(mo, self.pasta_user, 200)
        mo.action_ddfsc_submit()
        mo.with_user(self.manager).action_ddfsc_approve()
        mo.move_raw_ids[:1].move_line_ids[:1].quantity += 0.01
        result = mo.button_mark_done()
        self.assertEqual(result.get('tag'), 'display_notification')
        self.assertEqual(mo.ddfsc_approval_state, 'draft')
        self.assertNotEqual(mo.state, 'done')

    def test_sweepings_never_reduce_finished_goods(self):
        mo = self._mo(self.pasta_user, 'PASTA', 'product_pasta_long', 100)
        mo.action_confirm()
        self._stock_floor(mo)
        mo = self._produce(mo, self.pasta_user, 100)
        mo.write({'sweeping_qty': 4.0, 'scrap_qty': 2.0})
        mo.action_ddfsc_submit()
        mo.with_user(self.manager).action_ddfsc_approve()
        result = mo.button_mark_done()
        if isinstance(result, dict) and result.get('res_model') == 'mrp.consumption.warning':
            self.env['mrp.consumption.warning'].with_context(**result['context']).create({}).action_confirm()
        self.assertEqual(mo.state, 'done')
        finished = sum(self.env['stock.quant'].search([
            ('lot_id', 'in', mo.lot_producing_ids.ids), ('location_id', '=', mo.location_dest_id.id),
        ]).mapped('quantity'))
        self.assertEqual(finished, 100)

    def test_night_shift_after_midnight_is_the_same_shift(self):
        night = self.env.ref('ddfsc_manufacturing.shift_3')
        self.pasta_user.tz = 'Africa/Addis_Ababa'
        start = datetime(2026, 12, 1, 20, 0)                 # 23:00 local
        self._mo(self.pasta_user, 'PASTA', 'product_pasta_long', 10, night, start)
        with self.assertRaises(ValidationError):
            self._mo(self.pasta_user, 'PASTA', 'product_pasta_long', 10, night, start + timedelta(hours=2))

    def test_ingredient_request_follows_the_order_floor(self):
        """A Macaroni order's flour must arrive on the Macaroni floor, not Pasta's."""
        mo = self._mo(self.pasta_user, 'MAC', 'product_pasta_short', 100)
        mo.action_confirm()
        action = mo.action_request_ingredients()
        request = self.env['ddfsc.store.request'].with_user(self.pasta_user).with_context(
            **action['context']).create({})
        self.assertEqual(request.location_dest_id, mo.location_src_id)
        self.assertEqual(request.location_dest_id, self.env.ref('ddfsc_manufacturing.loc_macaroni'))


@tagged('post_install', '-at_install')
class TestFactoryShifts(TransactionCase):
    """Three 8-hour shifts in factory time; Shift 3 (22:00-06:00) belongs to its start day."""

    def setUp(self):
        super().setUp()
        import pytz
        self.tz = pytz.timezone('Africa/Addis_Ababa')
        self.env.company.partner_id.tz = 'Africa/Addis_Ababa'
        self.s1, self.s2, self.s3 = (self.env.ref('ddfsc_manufacturing.shift_%d' % i) for i in (1, 2, 3))

    def _utc(self, local):
        import pytz
        return self.tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)

    def test_boundaries(self):
        from datetime import date
        Shift = self.env['ddfsc.shift']
        cases = [
            (datetime(2026, 12, 1, 5, 59), self.s3, date(2026, 11, 30)),
            (datetime(2026, 12, 1, 6, 0), self.s1, date(2026, 12, 1)),
            (datetime(2026, 12, 1, 14, 0), self.s2, date(2026, 12, 1)),
            (datetime(2026, 12, 1, 22, 0), self.s3, date(2026, 12, 1)),
            (datetime(2026, 12, 2, 3, 0), self.s3, date(2026, 12, 1)),
        ]
        for local, shift, day in cases:
            self.assertEqual(Shift._shift_at(self._utc(local)), (shift, day), local)

    def test_production_day_ignores_user_timezone(self):
        from datetime import date
        line = self.env['mrp.workcenter'].search([('code', '=', 'PASTA')], limit=1)
        product = self.env.ref('ddfsc_manufacturing.product_pasta_long').product_variant_id
        self.env.user.tz = 'Europe/London'
        mo = self.env['mrp.production'].create({
            'product_id': product.id, 'product_qty': 1, 'ddfsc_line_id': line.id,
            'ddfsc_shift_id': self.s3.id, 'date_start': self._utc(datetime(2026, 12, 20, 1, 30)),
        })
        self.assertEqual(mo.ddfsc_production_date, date(2026, 12, 19))

    def test_overlapping_shift_refused(self):
        with self.assertRaises(ValidationError):
            self.env['ddfsc.shift'].create({'name': 'Overlap', 'code': 'OVL', 'hour_from': 13, 'hour_to': 15})

    def test_backorder_does_not_inherit_shift(self):
        line = self.env['mrp.workcenter'].search([('code', '=', 'PASTA')], limit=1)
        product = self.env.ref('ddfsc_manufacturing.product_pasta_long').product_variant_id
        mo = self.env['mrp.production'].create({
            'product_id': product.id, 'product_qty': 10, 'ddfsc_line_id': line.id,
            'ddfsc_shift_id': self.s1.id, 'scrap_qty': 3,
        })
        values = mo._get_backorder_mo_vals()
        copied = mo.copy_data(default=values)[0]
        self.assertFalse(copied.get('ddfsc_shift_id'))
        self.assertFalse(copied.get('scrap_qty'))
