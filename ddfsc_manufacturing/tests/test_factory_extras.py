from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFactoryExtras(TransactionCase):
    """Stores, documents, mill figures, reports and maintenance, as real users."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, department=False):
            return Users.create({
                'name': login, 'login': login, 'ddfsc_department': department,
                'group_ids': [Command.set([cls.env.ref(g).id for g in ['base.group_user'] + groups])],
            })

        cls.mill_user = user('fx_mill', ['mrp.group_mrp_user'], 'flour')
        cls.store_keeper = user('fx_store', ['stock.group_stock_manager'])
        cls.mechanic = user('fx_mech', ['maintenance.group_equipment_manager', 'stock.group_stock_user'])
        cls.ref = lambda self, xmlid: self.env.ref('ddfsc_manufacturing.%s' % xmlid)

    def _variant(self, xmlid):
        return self.env.ref('ddfsc_manufacturing.%s' % xmlid).product_variant_id

    def test_products_are_put_away_in_their_store(self):
        stock = self.env.ref('stock.stock_location_stock')
        sugar = self._variant('product_sugar')
        film = self._variant('product_zebib_film')
        self.assertEqual(stock._get_putaway_strategy(sugar), self.ref('loc_store_ingredients'))
        self.assertEqual(stock._get_putaway_strategy(film), self.ref('loc_store_packing'))
        self.assertEqual(self.ref('loc_store')._get_putaway_strategy(self._variant('product_biscuit_breakage')),
                         self.ref('loc_store_byproduct'))
        self.assertEqual(self.ref('loc_finished')._get_putaway_strategy(self._variant('product_zebib')),
                         self.ref('loc_fg_biscuit'))
        self.assertTrue(self.ref('loc_transit_asama'))

    def test_delivery_order_prints_receiver_and_gate_pass_copy(self):
        customer = self.env['res.partner'].create({'name': 'FX Customer'})
        out_type = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1).out_type_id
        picking = self.env['stock.picking'].with_user(self.store_keeper).create({
            'picking_type_id': out_type.id, 'partner_id': customer.id,
            'location_id': self.ref('loc_finished').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'ddfsc_receiver_name': 'Mohammed Abdusalam', 'ddfsc_receiver_identification': 'ID-4411',
            'ddfsc_vehicle_plate': '3-98673', 'ddfsc_customer_reference': 'CRSVH-00481-26',
            'move_ids': [Command.create({
                'product_id': self._variant('product_zebib').id, 'product_uom_qty': 10, 'ddfsc_bags': 0,
                'location_id': self.ref('loc_finished').id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            })],
        })
        self.assertEqual(picking._ddfsc_voucher_kind(), 'delivery_order')
        html, _kind = self.env['ir.actions.report'].with_user(self.store_keeper)._render_qweb_html(
            'ddfsc_manufacturing.action_report_picking_voucher', picking.ids)
        html = html.decode()
        for text in ('Delivery Order', 'PAOF/PA/534', 'Mohammed Abdusalam', 'ID-4411', 'Gate Pass', 'CRSVH-00481-26'):
            self.assertIn(text, html)

    def test_mill_bags_become_components_and_scale_figures(self):
        mo = self.env['mrp.production'].with_user(self.mill_user).with_context(ddfsc_department='flour').create({
            'product_id': self._variant('product_flour_scp').id, 'product_qty': 10,
            'ddfsc_line_id': self.env['mrp.workcenter'].search([('code', '=', 'MILL')], limit=1).id,
            'ddfsc_shift_id': self.env.ref('ddfsc_manufacturing.shift_1').id,
            'date_start': fields.Datetime.now(),
        })
        mo.action_confirm()
        mo.write({'mill_bags_50': 18, 'mill_bags_100': 3, 'mill_scale_start': 1880, 'mill_scale_end': 1874,
                  'mill_impurity_kg': 20})
        bags = mo._ddfsc_packing_moves()
        self.assertEqual(sorted(bags.mapped('product_uom_qty')), [3, 18])
        self.assertEqual(mo.mill_scale_wheat_qtl, 12.0)
        lines = mo.sudo().ddfsc_variance_line_ids.filtered(lambda line: line.move_id in bags)
        self.assertTrue(all(lines.mapped('is_packing')))
        self.assertFalse(lines & mo._ddfsc_variances_over_tolerance())
        mo.mill_bags_100 = 0
        self.assertEqual(len(mo._ddfsc_packing_moves()), 1)

        biscuit = self.env['mrp.production'].create({
            'product_id': self._variant('product_zebib').id, 'product_qty': 30,
            'ddfsc_line_id': self.env['mrp.workcenter'].search([('code', '=', 'BISC-CN')], limit=1).id,
        })
        with self.assertRaises(ValidationError):
            biscuit.mill_bags_50 = 2

    def test_stock_card_has_running_balance(self):
        product = self._variant('product_salt')
        store = self.ref('loc_store_ingredients')
        supplier = self.env.ref('stock.stock_location_suppliers')
        for qty in (40.0, 15.0):
            move = self.env['stock.move'].create({
                'product_id': product.id, 'product_uom_qty': qty, 'product_uom': product.uom_id.id,
                'location_id': supplier.id, 'location_dest_id': store.id,
            })
            move._action_confirm()
            move.quantity = qty
            move.picked = True
            move._action_done()
        self.env.flush_all()
        cards = self.env['ddfsc.stock.card'].with_user(self.store_keeper).search(
            [('product_id', '=', product.id), ('location_id', '=', store.id)], order='date, id')
        self.assertEqual(cards[-2:].mapped('received'), [40.0, 15.0])
        self.assertEqual(cards[-1].balance - cards[-2].balance, 15.0)

    def test_critical_items_and_production_report(self):
        wizard = self.env['ddfsc.critical.items.wizard'].with_user(self.store_keeper).create({
            'product_ids': [Command.set([self._variant('product_sugar').id])]})
        action = wizard.action_compute()
        self.assertEqual(action['res_model'], 'ddfsc.critical.items.line')
        self.assertEqual(wizard.line_ids.product_id, self._variant('product_sugar'))

        report = self.env['ddfsc.production.report.wizard'].with_user(self.mill_user).create({'department': 'biscuit'})
        html, _kind = self.env['ir.actions.report'].with_user(self.mill_user)._render_qweb_html(
            'ddfsc_manufacturing.action_report_department_production', report.ids)
        html = html.decode()
        self.assertIn('Production Report', html)
        self.assertIn('Biscuit', html)

    def test_maintenance_request_issues_spare_parts(self):
        spare = self.env['product.product'].create({
            'name': 'FX Bearing 6205', 'default_code': 'FX-6205', 'is_storable': True, 'standard_price': 350.0})
        self.env['stock.quant']._update_available_quantity(spare, self.ref('loc_store_spares'), 5.0)
        equipment = self.env['maintenance.equipment'].search([('serial_no', '=', 'BISC-CN-OVEN')], limit=1)
        request = self.env['maintenance.request'].with_user(self.mechanic).create({
            'name': 'Oven bearing', 'equipment_id': equipment.id, 'maintenance_type': 'corrective',
            'ddfsc_downtime_hours': 1.5, 'ddfsc_labour_cost': 200.0, 'ddfsc_manpower': 2,
            'ddfsc_spare_line_ids': [Command.create({'product_id': spare.id, 'quantity': 2})],
        })
        self.assertEqual(request.ddfsc_total_cost, 900.0)
        request.action_issue_spare_parts()
        picking = request.ddfsc_spare_picking_id
        self.assertEqual(picking.location_id, self.ref('loc_store_spares'))
        self.assertEqual(picking.location_dest_id, self.ref('loc_maintenance_use'))

    def test_preventive_plan_types(self):
        oven = self.env['maintenance.equipment'].search([('serial_no', '=', 'BISC-CN-OVEN')], limit=1)
        plans = self.env['maintenance.request'].search([
            ('equipment_id', '=', oven.id), ('maintenance_type', '=', 'preventive')])
        self.assertEqual(set(plans.mapped('ddfsc_pm_type')), {'inspection', 'lubrication', 'service'})
        self.assertTrue(self.env['maintenance.equipment'].search([('serial_no', '=', 'BISC-CN-COOLING')]))

    def test_extraction_rates_follow_the_milling_manual(self):
        from odoo.addons.ddfsc_manufacturing.models.mill import mill_extraction
        # Manual p. 215: 100 t wheat, 0.2 % silo loss, 2.5 t screenings, 4 t water, 75 t flour, 24 t bran.
        values = mill_extraction(100.0, 75.0, 24.0, 2.5, 0.2, 10.0, 1375 / 101.5)
        self.assertAlmostEqual(values['cer'], 74.85, places=2)
        self.assertAlmostEqual(values['water'], 4.0, places=6)
        self.assertAlmostEqual(values['ter'], 75 / 101.5 * 100, places=6)
        self.assertAlmostEqual(values['ep'], 75 / 99 * 100, places=6)
