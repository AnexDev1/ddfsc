from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSaleableByproducts(TransactionCase):

    def test_pasta_breakage_posts_to_its_own_temp_location(self):
        """A Pasta MO must create saleable breakage stock, not generic scrap."""
        pasta = self.env.ref('ddfsc_manufacturing.product_pasta_long').product_variant_id
        breakage = self.env.ref('ddfsc_manufacturing.product_pasta_breakage').product_variant_id
        line = self.env.ref('ddfsc_manufacturing.wc_pasta')
        location = self.env.ref('ddfsc_manufacturing.loc_pasta_byproduct')
        production = self.env['mrp.production'].create({
            'product_id': pasta.id,
            'product_uom_id': pasta.uom_id.id,
            'product_qty': 1,
            'ddfsc_line_id': line.id,
        })

        production._ddfsc_post_saleable_byproduct(breakage, 3)

        move = self.env['stock.move'].search([
            ('origin', '=', production.name),
            ('product_id', '=', breakage.id),
            ('location_dest_id', '=', location.id),
            ('state', '=', 'done'),
        ])
        self.assertEqual(len(move), 1)
        self.assertEqual(move.quantity, 3)
        self.assertTrue(breakage.sale_ok)

    def test_finished_goods_button_state_finds_existing_transfer(self):
        pasta = self.env.ref('ddfsc_manufacturing.product_pasta_long').product_variant_id
        line = self.env.ref('ddfsc_manufacturing.wc_pasta')
        production = self.env['mrp.production'].create({
            'product_id': pasta.id,
            'product_uom_id': pasta.uom_id.id,
            'product_qty': 1,
            'ddfsc_line_id': line.id,
        })
        request = self.env['ddfsc.store.request'].create({
            'production_id': production.id,
            'ddfsc_department': 'pasta',
            'request_type': 'finished_goods',
        })

        production._compute_ddfsc_fg_request()

        self.assertEqual(production.ddfsc_fg_request_id, request)
        self.assertEqual(production.ddfsc_fg_request_state, 'draft')

    def test_consumption_variance_keeps_bom_plan_when_actual_changes(self):
        flour = self.env.ref('ddfsc_manufacturing.product_flour_lcp').product_variant_id
        mill = self.env.ref('ddfsc_manufacturing.wc_mill')
        bom = self.env['mrp.bom'].search([('code', '=', 'MILL-LCP')], limit=1)
        production = self.env['mrp.production'].create({
            'product_id': flour.id,
            'product_uom_id': flour.uom_id.id,
            'product_qty': 1.0,
            'bom_id': bom.id,
            'ddfsc_line_id': mill.id,
        })

        production.action_confirm()
        wheat_move = production.move_raw_ids.filtered(
            lambda move: move.product_id == self.env.ref('ddfsc_manufacturing.product_wheat').product_variant_id
        )
        wheat_move.quantity = 1.40
        production._ddfsc_sync_variance_lines()
        variance = production.ddfsc_variance_line_ids.filtered(lambda line: line.move_id == wheat_move)

        self.assertEqual(production.ddfsc_planned_output_qty, 1.0)
        self.assertEqual(variance.planned_qty, 1.25)
        self.assertEqual(variance.actual_qty, 1.40)
        self.assertAlmostEqual(variance.variance_qty, 0.15, places=2)
