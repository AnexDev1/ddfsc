from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDowntime(TransactionCase):
    """Several stoppages per order, entered by a department user."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.biscuit_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'dt_biscuit', 'login': 'dt_biscuit', 'ddfsc_department': 'biscuit',
            'group_ids': [Command.set([cls.env.ref('base.group_user').id, cls.env.ref('mrp.group_mrp_user').id])],
        })
        cls.line = cls.env['mrp.workcenter'].search([('code', '=', 'BISC-CN')], limit=1)

    def _mo(self):
        return self.env['mrp.production'].with_user(self.biscuit_user).with_context(
            ddfsc_department='biscuit',
        ).create({
            'product_id': self.env.ref('ddfsc_manufacturing.product_zebib').product_variant_id.id,
            'product_qty': 30,
            'ddfsc_line_id': self.line.id,
            'ddfsc_shift_id': self.env.ref('ddfsc_manufacturing.shift_1').id,
            'date_start': fields.Datetime.now(),
        })

    def test_stoppages_add_up_and_longest_is_the_main_reason(self):
        mo = self._mo()
        mo.write({'ddfsc_downtime_line_ids': [
            Command.create({'reason': 'power', 'hours': 2.0}),
            Command.create({'reason': 'oven', 'hours': 1.5, 'note': 'Burner fault'}),
            Command.create({'reason': 'fg_full', 'hours': 0.5}),
        ]})
        self.assertEqual(mo.downtime_hours, 4.0)
        self.assertEqual(mo.downtime_reason, 'power')
        self.assertTrue(mo.ddfsc_has_equipment_downtime)

        mo.action_log_downtime()
        request = mo.ddfsc_maintenance_request_id
        self.assertEqual(request.equipment_id.ddfsc_downtime_code, 'oven')
        self.assertIn('1.5 hours', request.description)

    def test_supply_stoppage_does_not_open_maintenance(self):
        mo = self._mo()
        mo.write({'ddfsc_downtime_line_ids': [Command.create({'reason': 'fuel', 'hours': 8.0})]})
        self.assertFalse(mo.ddfsc_has_equipment_downtime)
        with self.assertRaises(UserError):
            mo.action_log_downtime()

    def test_hours_must_be_realistic(self):
        mo = self._mo()
        with self.assertRaises(UserError):
            mo.write({'ddfsc_downtime_line_ids': [Command.create({'reason': 'power', 'hours': 30.0})]})

    def test_biscuit_batches_follow_flour_used(self):
        self.assertEqual(self.line.ddfsc_batch_qtl, 1.5)
        mo = self._mo()
        self.assertAlmostEqual(mo.ddfsc_batches, mo.ddfsc_flour_used_qtl / 1.5)
